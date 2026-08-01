# -*- coding: utf-8 -*-
"""
========================================================
本地需求知识库 (RAG) — 中文 BM25 + SQLite，纯标准库，离线可用

设计目标
--------
用户要求「每次需求更改保持到本地需求知识库 RAG 中」。本模块提供一个
完全本地、无外部依赖、无联网的检索增强知识库：

1. 需求以 Markdown 文件存放在 `knowledge_base/requirements/`（受 git 版本管理，
   即需求文档同时进源码版本库）；
2. 索引数据库 `knowledge_base/requirements_kb.db`（构建产物，gitignore，可重建）
   记录文档/分块/倒排索引；
3. 检索采用中文感知的 BM25（中文按字 uni-gram + bi-gram；英文按词），
   支持按关键词召回最相关需求片段，供后续 LLM 增强（RAG）使用。

数据结构
--------
docs(id TEXT PK, title TEXT, date TEXT, requirement TEXT, status TEXT,
     path TEXT, updated_at TEXT)
chunks(id INTEGER PK, doc_id TEXT, idx INT, text TEXT, length INT)
inv(term TEXT, chunk_id INT, tf INT, PRIMARY KEY(term, chunk_id))

对外 API
--------
  kb = RequirementsKB()                       # 默认路径
  kb.ingest_dir('knowledge_base/requirements')  # 增量重建索引
  kb.add_document(doc_id, title, content, meta={})  # 单条写入
  kb.query('产业链 融合', top_k=5)              # 返回 [{doc, chunk, score}]
  kb.rebuild()                                # 清空并全量重建
"""
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# BM25 参数
K1 = 1.5
B = 0.75

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / 'knowledge_base' / 'requirements'
_DEFAULT_DB = Path(__file__).resolve().parents[2] / 'knowledge_base' / 'requirements_kb.db'


# ---------------------------------------------------------------------------
# 中文感知分词：CJK 字 uni-gram + bi-gram；英文/数字按词
# ---------------------------------------------------------------------------
_CJK = re.compile(r'[一-鿿]')
_ENG = re.compile(r'[a-z0-9]+')


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    low = text.lower()
    tokens: List[str] = []
    tokens.extend(_ENG.findall(low))
    cjk = _CJK.findall(low)
    tokens.extend(cjk)                       # 单字
    for i in range(len(cjk) - 1):            # 相邻二字 bi-gram
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


# ---------------------------------------------------------------------------
# 需求文档解析（轻量 front-matter：## 字段 标题 形式）
# ---------------------------------------------------------------------------
def _parse_markdown(path: Path) -> Dict[str, Any]:
    """从需求 md 解析出元信息 + 正文。约定：
    - 首行 `# 标题`
    - 其后若干 `**字段**：值` 行作为 meta
    - 其余为正文（按空行分块）
    """
    raw = path.read_text(encoding='utf-8')
    lines = raw.splitlines()
    title = ''
    meta: Dict[str, str] = {}
    body_lines: List[str] = []
    in_body = False
    if lines and lines[0].startswith('#'):
        title = lines[0].lstrip('#').strip()
        in_body = True
    for ln in lines[1:]:
        m = re.match(r'^\*\*(.+?)\*\*[：:]\s*(.+)$', ln.strip())
        if not in_body and m:
            meta[m.group(1).strip()] = m.group(2).strip()
            continue
        if ln.strip() == '' and not body_lines:
            continue
        body_lines.append(ln)
        in_body = True
    content = '\n'.join(body_lines).strip()
    return {
        'title': title or path.stem,
        'date': meta.get('日期') or meta.get('date') or '',
        'requirement': meta.get('需求') or meta.get('requirement') or '',
        'status': meta.get('状态') or meta.get('status') or '',
        'content': content,
        'meta': meta,
    }


class RequirementsKB:
    def __init__(self, db_path: Optional[str] = None, req_dir: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.req_dir = Path(req_dir) if req_dir else _DEFAULT_DIR
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._init_schema()

    # -- schema -------------------------------------------------------------
    def _init_schema(self) -> None:
        c = self._conn
        c.executescript('''
        CREATE TABLE IF NOT EXISTS docs (
            id TEXT PRIMARY KEY,
            title TEXT,
            date TEXT,
            requirement TEXT,
            status TEXT,
            path TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT,
            idx INT,
            text TEXT,
            length INT
        );
        CREATE TABLE IF NOT EXISTS inv (
            term TEXT,
            chunk_id INT,
            tf INT,
            PRIMARY KEY(term, chunk_id)
        );
        CREATE INDEX IF NOT EXISTS ix_inv_term ON inv(term);
        CREATE INDEX IF NOT EXISTS ix_chunk_doc ON chunks(doc_id);
        ''')
        c.commit()

    # -- write --------------------------------------------------------------
    def add_document(self, doc_id: str, title: str, content: str,
                     meta: Optional[Dict[str, Any]] = None) -> None:
        meta = meta or {}
        # 先删旧
        self._delete_document(doc_id)
        cur = self._conn
        cur.execute(
            'INSERT INTO docs(id,title,date,requirement,status,path,updated_at) '
            'VALUES(?,?,?,?,?,?,?)',
            (doc_id, title, meta.get('date', ''), meta.get('requirement', ''),
             meta.get('status', ''), meta.get('path', ''),
             time.strftime('%Y-%m-%d %H:%M:%S')),
        )
        # 分块：按空行/标题切分，保留段落
        chunks = self._chunk_text(content)
        for idx, ch in enumerate(chunks):
            cur_c = cur.execute(
                'INSERT INTO chunks(doc_id,idx,text,length) VALUES(?,?,?,?)',
                (doc_id, idx, ch, len(tokenize(ch))),
            )
            chunk_id = cur_c.lastrowid
            tf: Dict[str, int] = {}
            for t in tokenize(ch):
                tf[t] = tf.get(t, 0) + 1
            for t, f in tf.items():
                cur.execute(
                    'INSERT INTO inv(term,chunk_id,tf) VALUES(?,?,?)',
                    (t, chunk_id, f),
                )
        cur.commit()

    def _delete_document(self, doc_id: str) -> None:
        cur = self._conn
        ids = [r[0] for r in cur.execute(
            'SELECT id FROM chunks WHERE doc_id=?', (doc_id,)).fetchall()]
        for cid in ids:
            cur.execute('DELETE FROM inv WHERE chunk_id=?', (cid,))
        cur.execute('DELETE FROM chunks WHERE doc_id=?', (doc_id,))
        cur.execute('DELETE FROM docs WHERE id=?', (doc_id,))
        cur.commit()

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 600) -> List[str]:
        paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        out: List[str] = []
        for p in paras:
            if len(p) <= max_chars:
                out.append(p)
            else:
                # 长段落按句切
                sents = re.split(r'(?<=[。！？;；])', p)
                buf = ''
                for s in sents:
                    if len(buf) + len(s) > max_chars and buf:
                        out.append(buf.strip())
                        buf = ''
                    buf += s
                if buf.strip():
                    out.append(buf.strip())
        return out

    # -- ingest dir ---------------------------------------------------------
    def ingest_dir(self, req_dir: Optional[str] = None) -> int:
        d = Path(req_dir) if req_dir else self.req_dir
        if not d.exists():
            return 0
        count = 0
        for md in sorted(d.glob('*.md')):
            parsed = _parse_markdown(md)
            self.add_document(
                doc_id=md.stem,
                title=parsed['title'],
                content=parsed['content'],
                meta={
                    'date': parsed['date'],
                    'requirement': parsed['requirement'],
                    'status': parsed['status'],
                    'path': str(md),
                },
            )
            count += 1
        return count

    # -- rebuild ------------------------------------------------------------
    def rebuild(self, req_dir: Optional[str] = None) -> int:
        self._conn.executescript(
            'DELETE FROM inv; DELETE FROM chunks; DELETE FROM docs;')
        self._conn.commit()
        return self.ingest_dir(req_dir)

    # -- query --------------------------------------------------------------
    def query(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        q_tokens = tokenize(text)
        if not q_tokens:
            return []
        cur = self._conn
        # N, avgdl
        row = cur.execute(
            'SELECT COUNT(*), COALESCE(SUM(length),0) FROM chunks').fetchone()
        n_chunks = row[0] or 0
        avgdl = (row[1] / n_chunks) if n_chunks else 0.0
        if n_chunks == 0:
            return []

        # df per term
        scores: Dict[int, float] = {}
        chunk_cache: Dict[int, Dict[str, Any]] = {}
        for t in set(q_tokens):
            postings = cur.execute(
                'SELECT chunk_id, tf FROM inv WHERE term=?', (t,)).fetchall()
            df = len(postings)
            if df == 0:
                continue
            idf = (n_chunks - df + 0.5) / (df + 0.5)
            idf = max(0.0, __import__('math').log(1.0 + idf))
            for chunk_id, tf in postings:
                if chunk_id not in chunk_cache:
                    r = cur.execute(
                        'SELECT doc_id, text, length FROM chunks WHERE id=?',
                        (chunk_id,)).fetchone()
                    chunk_cache[chunk_id] = {
                        'doc_id': r[0], 'text': r[1], 'length': r[2] or 0}
                dl = chunk_cache[chunk_id]['length']
                denom = tf + K1 * (1 - B + B * (dl / avgdl if avgdl else 0))
                scores[chunk_id] = scores.get(chunk_id, 0.0) + idf * (
                    tf * (K1 + 1) / denom)
        # 汇总到文档级别并取 top_k 文档；同时记录每文档最高分句块的 cid
        doc_scores: Dict[str, float] = {}
        doc_best_cid: Dict[str, int] = {}
        for cid, sc in scores.items():
            did = chunk_cache[cid]['doc_id']
            if sc > doc_scores.get(did, 0.0):
                doc_scores[did] = sc
                doc_best_cid[did] = cid
        ranked = sorted(doc_scores.items(), key=lambda x: -x[1])[:top_k]
        result: List[Dict[str, Any]] = []
        for doc_id, sc in ranked:
            d = cur.execute(
                'SELECT title,date,requirement,status FROM docs WHERE id=?',
                (doc_id,)).fetchone()
            best_chunk = chunk_cache.get(doc_best_cid.get(doc_id, -1))
            result.append({
                'doc_id': doc_id,
                'title': d[0] if d else doc_id,
                'date': d[1] if d else '',
                'requirement': d[2] if d else '',
                'status': d[3] if d else '',
                'score': round(sc, 4),
                'snippet': best_chunk['text'][:240] if best_chunk else '',
            })
        return result

    def close(self) -> None:
        self._conn.close()


def main() -> None:
    import sys
    kb = RequirementsKB()
    if len(sys.argv) > 1 and sys.argv[1] == 'rebuild':
        n = kb.rebuild()
        print(f'rebuilt index, {n} documents')
    else:
        n = kb.ingest_dir()
        print(f'ingested {n} documents from {kb.req_dir}')
    kb.close()


if __name__ == '__main__':
    main()

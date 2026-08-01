<template>
  <div class="ics-sandbox" ref="root">
    <div class="app">
      <!-- ====== 顶部工具栏 ====== -->
      <div class="header">
        <div class="logo">
          <div class="logo-icon">⛓</div>
          <span>产业链全景可视化</span>
        </div>
        <div class="view-switcher">
          <button class="view-btn active" data-view="standard" @click="switchView('standard')">📊 标准视图</button>
          <button class="view-btn" data-view="simulation" @click="switchView('simulation')">🎬 推演沙盘</button>
          <button class="view-btn" data-view="company" @click="switchView('company')">🏢 公司穿透</button>
        </div>
        <div class="search-box">
          <span style="font-size:12px;color:hsl(var(--text-dim))">🔍</span>
          <input type="text" placeholder="搜索产业链/公司..." @input="handleSearch($event.target.value)">
        </div>
        <div style="display:flex;gap:4px">
          <button class="header-btn" @click="exportGraph()">📷 导出快照</button>
          <button class="header-btn primary" @click="toggleLiquidity()" id="liqBtn">💧 资金面图层</button>
          <button class="theme-toggle" @click="toggleTheme()" id="themeBtn">🌙</button>
        </div>
      </div>

      <div class="main">
        <!-- ====== 左侧面板 ====== -->
        <div class="left-panel">
          <div class="panel-section">
            <div class="panel-title">📂 产业链目录</div>
            <div id="chainList"></div>
          </div>
          <div class="panel-section" id="shockSection">
            <div class="panel-title">⚡ 外部冲击事件库 <span style="font-size:9px;color:hsl(var(--text-dim));font-weight:400">(拖拽至图谱)</span></div>
            <div id="shockList"></div>
          </div>
          <div class="panel-section" id="layerSection">
            <div class="panel-title">🎛 传导类型筛选</div>
            <div class="layer-toggles">
              <div class="layer-chip cost active" data-type="cost" @click="toggleEdgeType('cost',$event.currentTarget)">C 成本传导</div>
              <div class="layer-chip demand active" data-type="demand" @click="toggleEdgeType('demand',$event.currentTarget)">D 需求拉动</div>
              <div class="layer-chip subst active" data-type="subst" @click="toggleEdgeType('subst',$event.currentTarget)">S 替代竞争</div>
              <div class="layer-chip supply active" data-type="supply" @click="toggleEdgeType('supply',$event.currentTarget)">Sup 供给约束</div>
            </div>
          </div>
          <div class="panel-section" id="simControls" style="display:none">
            <div class="panel-title">⚙️ 冲击参数</div>
            <div class="shock-controls">
              <div class="shock-control-row">
                <span class="shock-control-label">强度</span>
                <input type="range" class="shock-slider" min="10" max="100" value="60" @input="updateShockParam('intensity',$event.target.value)">
                <span class="shock-value" id="intensityVal">60%</span>
              </div>
              <div class="shock-control-row">
                <span class="shock-control-label">持续</span>
                <input type="range" class="shock-slider" min="3" max="30" value="10" @input="updateShockParam('duration',$event.target.value)">
                <span class="shock-value" id="durationVal">10d</span>
              </div>
              <div class="shock-control-row">
                <span class="shock-control-label">衰减</span>
                <input type="range" class="shock-slider" min="0" max="50" value="20" @input="updateShockParam('decay',$event.target.value)">
                <span class="shock-value" id="decayVal">20%</span>
              </div>
              <button class="header-btn primary" style="width:100%;justify-content:center;margin-top:4px" @click="runSimulation()">▶ 启动推演</button>
            </div>
          </div>
        </div>

        <!-- ====== 中央画布 ====== -->
        <div class="center-area">
          <div class="canvas-container" id="canvasContainer">
            <div class="liquidity-overlay" id="liqOverlay"></div>
            <div class="canvas-toolbar">
              <div class="canvas-btn" @click="zoomCanvas(1.2)" title="放大">+</div>
              <div class="canvas-btn" @click="zoomCanvas(0.8)" title="缩小">−</div>
              <div class="canvas-btn" @click="resetCanvas()" title="重置">⟲</div>
              <div class="canvas-btn" @click="fitCanvas()" title="适应">⊡</div>
            </div>
            <svg id="graphSvg" width="1400" height="900" style="min-width:100%"></svg>
            <div class="legend" id="legendBox">
              <div class="legend-title">传导类型</div>
              <div class="legend-item"><div class="legend-line" style="background:hsl(var(--cost))"></div>成本传导</div>
              <div class="legend-item"><div class="legend-line" style="background:hsl(var(--demand))"></div>需求拉动</div>
              <div class="legend-item"><div class="legend-line" style="background:hsl(var(--subst));background-image:repeating-linear-gradient(90deg,hsl(var(--subst)) 0 4px,transparent 4px 8px)"></div>替代竞争</div>
              <div class="legend-item"><div class="legend-line" style="background:hsl(var(--supply));height:3px"></div>供给约束</div>
              <div style="border-top:1px solid hsl(var(--border));margin-top:4px;padding-top:4px">
                <div class="legend-item"><div class="legend-node" style="background:hsl(var(--up) / 0.3);border:1px solid hsl(var(--up))"></div>利好</div>
                <div class="legend-item"><div class="legend-node" style="background:hsl(var(--down) / 0.3);border:1px solid hsl(var(--down))"></div>利空</div>
                <div class="legend-item"><div class="legend-node" style="background:hsl(var(--bg-card));border:1px solid hsl(var(--border-strong))"></div>中性</div>
              </div>
            </div>
          </div>
          <!-- 时间轴（仅推演模式显示） -->
          <div class="timeline-bar" id="timelineBar" style="display:none">
            <button class="timeline-btn play" @click="togglePlay()" id="playBtn">▶</button>
            <button class="timeline-btn" @click="stepTimeline(-1)">⏮</button>
            <button class="timeline-btn" @click="stepTimeline(1)">⏭</button>
            <div class="timeline-track">
              <div class="timeline-rail"></div>
              <div class="timeline-progress" id="tlProgress" style="width:0%"></div>
              <div class="timeline-handle" id="tlHandle" style="left:0%"></div>
              <div class="timeline-ticks" id="tlTicks"></div>
            </div>
            <span class="timeline-label" id="tlLabel">T+0d</span>
          </div>
        </div>

        <!-- ====== 右侧信息面板 ====== -->
        <div class="right-panel" id="rightPanel"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { listIndustryChains, getIndustryChain, listShocks } from '@/api/industryChain'

// 根节点 ref：所有 DOM 查询收敛到组件内，避免污染全局
const root = ref(null)

function el(id) {
  return root.value ? root.value.querySelector('#' + id) : null
}

// 懒加载单条产业链完整图谱（目录只含摘要，图谱按需拉取）
async function ensureChainLoaded(id) {
  const c = INDUSTRY_CHAINS[id]
  if (c && c.nodes) return c
  const data = await getIndustryChain(id)
  INDUSTRY_CHAINS[id] = Object.assign({}, c, data)
  return INDUSTRY_CHAINS[id]
}

// 生成式 innerHTML 的交互函数需挂到 window，供内联 onclick 解析
function bindWindow() {
  window.selectChain = (id) => selectChain(id).catch((e) => console.error('[ics] selectChain', e))
  window.selectShock = selectShock
  window.onNodeClick = onNodeClick
  window.onEdgeClick = onEdgeClick
  window.onShockDragStart = onShockDragStart
  window.onShockDragEnd = onShockDragEnd
  window.generateAIReport = generateAIReport
  window.switchInfoTab = switchInfoTab
  window.onCompanyClick = onCompanyClick
}
function unbindWindow() {
  ;['selectChain', 'selectShock', 'onNodeClick', 'onEdgeClick', 'onShockDragStart', 'onShockDragEnd', 'generateAIReport', 'switchInfoTab', 'onCompanyClick'].forEach((k) => { try { delete window[k] } catch (e) {} })
}

// ============================================================
//  数据层 — 锂电池产业链（完整示例）
// ============================================================

let INDUSTRY_CHAINS = {}
let SHOCK_EVENTS = []


// ============================================================
//  状态管理
// ============================================================
let state = {
  currentChain: 'lithium',
  currentView: 'standard',
  selectedNode: null,
  selectedShock: null,
  edgeTypes: { cost: true, demand: true, subst: true, supply: true },
  liquidityActive: false,
  simPlaying: false,
  simStep: 0,
  simTotal: 20,
  zoom: 1,
  shockParams: { intensity: 60, duration: 10, decay: 20 },
};

const LAYER_LABELS = ['上游资源', '上游材料/设备', '中游制造', '配套服务', '下游终端'];
const LAYER_X = [120, 360, 620, 860, 1120];
const EDGE_COLORS = { cost: 'var(--cost)', demand: 'var(--demand)', subst: 'var(--subst)', supply: 'var(--supply)' };
const EDGE_LABELS = { cost: 'C', demand: 'D', subst: 'S', supply: 'Sup' };

// ============================================================
//  渲染 — 左侧面板
// ============================================================
function renderChainList() {
  const html = Object.values(INDUSTRY_CHAINS).map(c => `
    <div class="chain-item ${c.id === state.currentChain ? 'active' : ''}" onclick="selectChain('${c.id}')">
      <div class="chain-icon" style="background:hsl(${c.color} / 0.15);color:hsl(${c.color})">${c.icon}</div>
      <span>${c.name}</span>
    </div>
  `).join('');
  el('chainList').innerHTML = html;
}

function renderShockList() {
  const html = SHOCK_EVENTS.map(s => {
    const color = s.cat === 'policy' ? 'hsl(220 80% 70%)' :
                  s.cat === 'geo' ? 'hsl(0 80% 70%)' :
                  s.cat === 'sentiment' ? 'hsl(38 100% 65%)' : 'hsl(280 80% 70%)';
    const fillWidth = s.intensity;
    const fillColor = s.cat === 'policy' ? 'hsl(220 80% 50%)' :
                      s.cat === 'geo' ? 'hsl(0 80% 50%)' :
                      s.cat === 'sentiment' ? 'hsl(38 100% 50%)' : 'hsl(280 80% 50%)';
    return `
      <div class="shock-card ${state.selectedShock === s.id ? 'selected' : ''}"
           draggable="true"
           ondragstart="onShockDragStart(event,'${s.id}')"
           ondragend="onShockDragEnd(event)"
           onclick="selectShock('${s.id}')">
        <span class="shock-tag ${s.cat}">${s.cat === 'policy' ? '政策' : s.cat === 'geo' ? '地缘' : s.cat === 'sentiment' ? '舆情' : '资金'}</span>
        <div class="shock-name">${s.name}</div>
        <div class="shock-desc">${s.desc}</div>
        <div class="shock-intensity">
          <span style="font-size:10px;color:hsl(var(--text-dim))">强度</span>
          <div class="intensity-bar"><div class="intensity-fill" style="width:${fillWidth}%;background:${fillColor}"></div></div>
          <span class="mono" style="font-size:10px;color:${color}">${s.intensity}%</span>
        </div>
      </div>
    `;
  }).join('');
  el('shockList').innerHTML = html;
}

// ============================================================
//  渲染 — 图谱 SVG
// ============================================================
function getNodeColor(node, impact) {
  if (impact === 'positive') return 'hsl(var(--up))';
  if (impact === 'negative') return 'hsl(var(--down))';
  return 'hsl(var(--border-strong))';
}

function getNodeSize(size) {
  return { large: { w: 130, h: 42 }, medium: { w: 110, h: 38 }, small: { w: 90, h: 34 } }[size] || { w: 100, h: 38 };
}

function layoutNodes(chain) {
  // 按层分组
  const layers = {};
  chain.nodes.forEach(n => {
    const l = n.layer;
    if (!layers[l]) layers[l] = [];
    layers[l].push(n);
  });

  // 计算位置
  const positions = {};
  const layerKeys = Object.keys(layers).map(Number).sort((a, b) => a - b);
  const layerMap = { 0: 0, 0.5: 1, 1: 2, 1.5: 3, 2: 4 };
  const canvasH = 760;
  const startY = 60;

  layerKeys.forEach(lk => {
    const nodes = layers[lk];
    const xIdx = layerMap[lk] !== undefined ? layerMap[lk] : 2;
    const x = LAYER_X[xIdx] || 620;
    const totalH = canvasH - startY * 2;
    const gap = totalH / Math.max(nodes.length, 1);
    nodes.forEach((n, i) => {
      positions[n.id] = { x, y: startY + gap * (i + 0.5) };
    });
  });

  return positions;
}

function renderGraph() {
  const chain = INDUSTRY_CHAINS[state.currentChain];
  const positions = layoutNodes(chain);
  const svg = el('graphSvg');

  // 计算画布大小
  const maxX = Math.max(...Object.values(positions).map(p => p.x)) + 200;
  const maxY = Math.max(...Object.values(positions).map(p => p.y)) + 100;
  svg.setAttribute('width', Math.max(maxX, 1200) * state.zoom);
  svg.setAttribute('height', Math.max(maxY, 800) * state.zoom);
  svg.setAttribute('viewBox', `0 0 ${maxX} ${maxY}`);

  let svgContent = '';

  // 层背景
  const layerBg = [
    { x: 20, label: '上游资源/原料' },
    { x: 260, label: '材料/设备' },
    { x: 520, label: '中游制造' },
    { x: 760, label: '配套服务' },
    { x: 1020, label: '下游终端' },
  ];
  layerBg.forEach(lb => {
    svgContent += `<rect x="${lb.x}" y="20" width="220" height="${maxY - 40}" rx="8" fill="hsl(var(--bg-card) / 0.3)" stroke="hsl(var(--border) / 0.3)" stroke-width="1" stroke-dasharray="4 4" />`;
    svgContent += `<text x="${lb.x + 110}" y="38" text-anchor="middle" fill="hsl(var(--text-dim))" font-size="10" font-weight="600">${lb.label}</text>`;
  });

  // 连线
  chain.edges.forEach((e, idx) => {
    if (!state.edgeTypes[e.type]) return;
    const sp = positions[e.source];
    const tp = positions[e.target];
    if (!sp || !tp) return;

    const ns = chain.nodes.find(n => n.id === e.source);
    const nt = chain.nodes.find(n => n.id === e.target);
    const nsSize = getNodeSize(ns.size);
    const ntSize = getNodeSize(nt.size);

    const x1 = sp.x + nsSize.w;
    const y1 = sp.y;
    const x2 = tp.x;
    const y2 = tp.y;

    // 贝塞尔曲线
    const midX = (x1 + x2) / 2;
    const path = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;

    const color = `hsl(${EDGE_COLORS[e.type]})`;
    const dashArray = e.type === 'subst' ? '5 4' : 'none';
    const strokeWidth = e.type === 'supply' ? 2.5 : 1.5;

    // 判断是否在推演路径中
    const inSimPath = state.currentView === 'simulation' && state.simStep > 0 &&
      isEdgeInSimPath(e.source, e.target);

    let lineClass = 'edge-line';
    let opacity = 0.5;
    if (inSimPath) {
      lineClass += ' flow-line';
      opacity = 1;
    } else if (state.currentView === 'simulation' && state.simStep > 0) {
      opacity = 0.1;
    }

    svgContent += `<path class="${lineClass}" d="${path}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-dasharray="${dashArray}" opacity="${opacity}" data-edge="${idx}" onclick="onEdgeClick(${idx})" />`;

    // 边标签
    const labelX = midX;
    const labelY = (y1 + y2) / 2;
    svgContent += `<text class="edge-label" x="${labelX}" y="${labelY - 6}" text-anchor="middle" opacity="${opacity}">${EDGE_LABELS[e.type]}</text>`;
    svgContent += `<text class="edge-label" x="${labelX}" y="${labelY + 8}" text-anchor="middle" opacity="${opacity * 0.7}">coeff=${e.coeff}</text>`;
  });

  // 节点
  chain.nodes.forEach(n => {
    const pos = positions[n.id];
    if (!pos) return;
    const size = getNodeSize(n.size);
    const impact = getNodeImpact(n.id);
    const borderColor = getNodeColor(n, impact);
    const bgColor = impact === 'positive' ? 'hsl(var(--up) / 0.12)' :
                    impact === 'negative' ? 'hsl(var(--down) / 0.12)' :
                    'hsl(var(--bg-card))';

    const isSelected = state.selectedNode === n.id;
    const isDimmed = state.selectedNode && state.selectedNode !== n.id && !isConnectedTo(n.id, state.selectedNode);
    let nodeClass = n.type === 'industry' ? 'node-rect' : 'node-circle';
    if (isDimmed) nodeClass += ' dimmed';

    // 推演动画
    const isSimActive = state.currentView === 'simulation' && state.simStep > 0 && impact;
    if (isSimActive) nodeClass += ' pulse-node';

    if (n.type === 'industry') {
      svgContent += `<rect class="${nodeClass}" x="${pos.x}" y="${pos.y - size.h/2}" width="${size.w}" height="${size.h}" rx="6" fill="${bgColor}" stroke="${borderColor}" stroke-width="${isSelected ? 2.5 : 1.5}" data-node="${n.id}" onclick="onNodeClick('${n.id}')" />`;
      svgContent += `<text class="node-label" x="${pos.x + size.w/2}" y="${pos.y - 2}" text-anchor="middle">${n.label}</text>`;
      svgContent += `<text class="node-sublabel" x="${pos.x + size.w/2}" y="${pos.y + 12}" text-anchor="middle">${n.sub}</text>`;
    } else {
      svgContent += `<circle class="${nodeClass}" cx="${pos.x + size.w/2}" cy="${pos.y}" r="20" fill="${bgColor}" stroke="${borderColor}" stroke-width="${isSelected ? 2.5 : 1.5}" data-node="${n.id}" onclick="onNodeClick('${n.id}')" />`;
      svgContent += `<text class="node-label" x="${pos.x + size.w/2}" y="${pos.y + 4}" text-anchor="middle">${n.label}</text>`;
    }

    // 冲击源标记
    if (state.selectedShock) {
      const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
      if (shock && shock.target === n.id) {
        svgContent += `<circle cx="${pos.x + size.w}" cy="${pos.y - size.h/2}" r="6" fill="hsl(var(--warn))" class="pulse-node" />`;
        svgContent += `<text x="${pos.x + size.w + 10}" y="${pos.y - size.h/2 + 3}" fill="hsl(var(--warn))" font-size="10" font-weight="600">⚡冲击源</text>`;
      }
    }

    // 公司穿透视图：显示公司数量
    if (state.currentView === 'company' && chain.companies[n.id]) {
      const count = chain.companies[n.id].length;
      svgContent += `<circle cx="${pos.x + size.w - 5}" cy="${pos.y + size.h/2 - 5}" r="8" fill="hsl(var(--primary))" />`;
      svgContent += `<text x="${pos.x + size.w - 5}" y="${pos.y + size.h/2 - 2}" text-anchor="middle" fill="hsl(var(--bg))" font-size="9" font-weight="700">${count}</text>`;
    }
  });

  // 推演模式：中间变量浮窗
  if (state.currentView === 'simulation' && state.simStep > 0 && state.selectedShock) {
    const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
    if (shock && shock.midVars) {
      shock.midVars.forEach((mv, i) => {
        if (state.simStep >= (i + 1) * 3) {
          const targetNode = chain.nodes.find(n => n.id === shock.target);
          const pos = positions[shock.target];
          if (pos) {
            const fx = pos.x + 160;
            const fy = pos.y - 60 + i * 55;
            svgContent += `<g class="midvar-popup" transform="translate(${fx},${fy})">
              <rect x="0" y="0" width="180" height="48" rx="6" fill="hsl(var(--bg-elevated))" stroke="hsl(var(--warn) / 0.5)" stroke-width="1" filter="drop-shadow(0 4px 8px hsl(0 0% 0% / 0.3))" />
              <text x="8" y="14" fill="hsl(var(--warn))" font-size="11" font-weight="600">${mv.name}</text>
              <text x="150" y="14" fill="${mv.change.startsWith('+') || mv.change.startsWith('−') ? (mv.change.startsWith('+') ? 'hsl(var(--up))' : 'hsl(var(--down))') : 'hsl(var(--up))'}" font-size="11" font-weight="700" text-anchor="end" font-family="var(--mono)">${mv.change}</text>
              <text x="8" y="30" fill="hsl(var(--text-muted))" font-size="9">${mv.desc}</text>
              <text x="8" y="42" fill="hsl(var(--text-dim))" font-size="8">T+${(i+1)*3}d 传导到位</text>
            </g>`;
          }
        }
      });
    }
  }

  svg.innerHTML = svgContent;
}

function getNodeImpact(nodeId) {
  if (state.currentView !== 'simulation' || state.simStep === 0 || !state.selectedShock) return null;
  const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
  if (!shock) return null;

  const chain = INDUSTRY_CHAINS[state.currentChain];

  // 全局资金面冲击
  if (shock.target === '__global__') {
    if (state.simStep > 0) {
      // 高资本开支行业受损
      const node = chain.nodes.find(n => n.id === nodeId);
      if (node && (node.costSensitivity > 60 || node.barrier === 'high' || node.barrier === 'extreme')) {
        return 'negative';
      }
    }
    return null;
  }

  // 单点冲击传导
  const visited = simulateBFS(shock.target, state.simStep);
  const nodeImpact = visited[nodeId];
  return nodeImpact;
}

function simulateBFS(source, step) {
  const chain = INDUSTRY_CHAINS[state.currentChain];
  const impacts = {};
  impacts[source] = step >= 1 ? 'source' : null;

  const queue = [{ id: source, dist: 0, impact: 'source' }];
  const visited = new Set([source]);

  while (queue.length > 0) {
    const { id, dist, impact } = queue.shift();
    if (dist >= step) continue;

    chain.edges.forEach(e => {
      if (e.source === id && !visited.has(e.target)) {
        visited.add(e.target);
        const isNegative = e.type === 'cost' || e.type === 'supply';
        impacts[e.target] = isNegative ? 'negative' : 'positive';
        queue.push({ id: e.target, dist: dist + 1, impact: impacts[e.target] });
      }
      // 反向传导（需求拉动反向）
      if (e.target === id && e.type === 'demand' && !visited.has(e.source)) {
        visited.add(e.source);
        impacts[e.source] = 'positive';
        queue.push({ id: e.source, dist: dist + 1, impact: 'positive' });
      }
    });
  }

  // 源节点特殊处理
  if (impacts[source] === 'source') {
    const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
    impacts[source] = shock && shock.cat === 'sentiment' && shock.id !== 'tech_breakthrough' ? 'negative' : 'source';
  }

  return impacts;
}

function isEdgeInSimPath(source, target) {
  if (!state.selectedShock) return false;
  const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
  if (!shock) return false;
  if (shock.target === '__global__') return false;

  const visited = simulateBFS(shock.target, state.simStep);
  return visited[source] && visited[target];
}

function isConnectedTo(nodeId, targetId) {
  const chain = INDUSTRY_CHAINS[state.currentChain];
  return chain.edges.some(e =>
    (e.source === nodeId && e.target === targetId) ||
    (e.source === targetId && e.target === nodeId)
  );
}

// ============================================================
//  渲染 — 右侧面板
// ============================================================
function renderRightPanel() {
  const panel = el('rightPanel');
  const chain = INDUSTRY_CHAINS[state.currentChain];

  if (!state.selectedNode) {
    panel.innerHTML = `
      <div class="panel-section">
        <div class="panel-title">ℹ️ 产业链概览</div>
        <div class="node-info-row"><span class="node-info-label">链路名称</span><span class="node-info-value">${chain.name}</span></div>
        <div class="node-info-row"><span class="node-info-label">节点数</span><span class="node-info-value">${chain.nodes.length}</span></div>
        <div class="node-info-row"><span class="node-info-label">传导关系</span><span class="node-info-value">${chain.edges.length}</span></div>
        <div class="node-info-row"><span class="node-info-label">关联公司</span><span class="node-info-value">${Object.values(chain.companies).flat().length}</span></div>
      </div>
      <div class="panel-section">
        <div class="panel-title">📰 最新资讯</div>
        ${chain.news.map(n => `
          <div class="news-item">
            <span class="news-time">${n.time}</span>
            <div class="news-title">${n.title}</div>
          </div>
        `).join('')}
      </div>
      <div class="panel-section">
        <div class="ai-panel">
          <div class="ai-title">🤖 AI 产业链分析</div>
          <div class="ai-content">点击任意节点，AI 将自动生成该环节的深度分析报告，包括供需格局、成本结构、竞争态势和投资建议。</div>
          <button class="ai-btn" style="margin-top:8px" onclick="generateAIReport()">生成全链路分析报告</button>
        </div>
      </div>
    `;
    return;
  }

  const node = chain.nodes.find(n => n.id === state.selectedNode);
  if (!node) return;
  const companies = chain.companies[node.id] || [];
  const incomingEdges = chain.edges.filter(e => e.target === node.id);
  const outgoingEdges = chain.edges.filter(e => e.source === node.id);
  const nodeNews = chain.news.filter(n => n.tag === 'price' || n.tag === 'market' || n.tag === 'policy');

  const supplyDemandMap = { tight: '偏紧', surplus: '过剩', balanced: '平衡', growing: '成长', stable: '稳定', explosive: '爆发', oligopoly: '寡头', competitive: '竞争' };
  const barrierMap = { low: '低', medium: '中', high: '高', extreme: '极高' };

  panel.innerHTML = `
    <div class="info-tabs">
      <div class="info-tab active" onclick="switchInfoTab('basic',this)">📋 基础信息</div>
      <div class="info-tab" onclick="switchInfoTab('companies',this)">🏢 上市公司</div>
      <div class="info-tab" onclick="switchInfoTab('news',this)">📰 资讯</div>
    </div>
    <div id="infoTabContent">
      <div class="panel-section">
        <div class="panel-title">📌 ${node.label}</div>
        <div class="node-info-row"><span class="node-info-label">所属层级</span><span class="node-info-value">${node.sub}</span></div>
        <div class="node-info-row"><span class="node-info-label">定价权</span><span class="node-info-value">${'★'.repeat(Math.ceil(node.pricingPower/20))}<span style="color:hsl(var(--text-dim))">${'☆'.repeat(5-Math.ceil(node.pricingPower/20))}</span></span></div>
        <div class="node-info-row"><span class="node-info-label">产能壁垒</span><span class="node-info-value">${barrierMap[node.barrier] || node.barrier}</span></div>
        <div class="node-info-row"><span class="node-info-label">供需格局</span><span class="node-info-value">${supplyDemandMap[node.supplyDemand] || node.supplyDemand}</span></div>
        <div class="node-info-row"><span class="node-info-label">成本敏感度</span><span class="node-info-value ${node.costSensitivity > 60 ? 'down' : ''}">${node.costSensitivity}%</span></div>
        <div class="node-info-row"><span class="node-info-label">利润弹性</span><span class="node-info-value ${node.profitElasticity > 70 ? 'up' : ''}">${node.profitElasticity}%</span></div>
      </div>
      <div class="panel-section">
        <div class="panel-title">🔗 上游来源 (${incomingEdges.length})</div>
        ${incomingEdges.length ? incomingEdges.map(e => {
          const src = chain.nodes.find(n => n.id === e.source);
          return `<div class="node-info-row">
            <span class="node-info-label">${EDGE_LABELS[e.type]} ${src?.label || e.source}</span>
            <span class="node-info-value">coeff=${e.coeff} lag=${e.lag}d</span>
          </div>`;
        }).join('') : '<div style="font-size:11px;color:hsl(var(--text-dim))">无上游来源</div>'}
      </div>
      <div class="panel-section">
        <div class="panel-title">🔗 下游去向 (${outgoingEdges.length})</div>
        ${outgoingEdges.length ? outgoingEdges.map(e => {
          const tgt = chain.nodes.find(n => n.id === e.target);
          return `<div class="node-info-row">
            <span class="node-info-label">${EDGE_LABELS[e.type]} ${tgt?.label || e.target}</span>
            <span class="node-info-value">coeff=${e.coeff} lag=${e.lag}d</span>
          </div>`;
        }).join('') : '<div style="font-size:11px;color:hsl(var(--text-dim))">终端环节</div>'}
      </div>
      ${companies.length ? `
      <div class="panel-section">
        <div class="panel-title">🏢 关联上市公司 (${companies.length})</div>
        ${companies.map(c => `
          <div class="company-row" onclick="onCompanyClick('${c.code}')">
            <div class="company-header">
              <span class="company-name">${c.name}</span>
              <span class="company-code">${c.code}</span>
            </div>
            <div class="company-meta">
              <span>营收占比 ${c.revPct}%</span>
              <span>海外 ${c.overseas}%</span>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="font-size:10px;color:hsl(var(--text-dim))">敏感度</span>
              <div class="sensitivity-bar"><div class="sensitivity-fill" style="width:${c.sensitivity*100}%;background:${c.sensitivity > 0.8 ? 'hsl(var(--up))' : c.sensitivity > 0.6 ? 'hsl(var(--warn))' : 'hsl(var(--text-muted))'}"></div></div>
              <span class="mono" style="font-size:10px;color:hsl(var(--text-muted))">${(c.sensitivity*100).toFixed(0)}%</span>
            </div>
          </div>
        `).join('')}
      </div>` : ''}
      <div class="panel-section">
        <div class="ai-panel">
          <div class="ai-title">🤖 AI 深度分析</div>
          <div class="ai-content">基于当前节点 ${node.label} 的产业链位置、供需格局和关联公司，AI 将生成：</div>
          <div style="font-size:11px;color:hsl(var(--text-muted));margin-top:6px;line-height:1.6">
            • 环节基本面分析（供需/价格/成本）<br>
            • 上下游传导逻辑解读<br>
            • 关键公司投资弹性评估<br>
            • 潜在风险与催化剂
          </div>
          <button class="ai-btn" style="margin-top:8px" onclick="generateAIReport()">生成 ${node.label} 分析报告</button>
        </div>
      </div>
    </div>
  `;
}

function renderCompanyView() {
  const panel = el('rightPanel');
  const chain = INDUSTRY_CHAINS[state.currentChain];

  if (!state.selectedNode) {
    const allCompanies = Object.entries(chain.companies).map(([nodeId, comps]) => {
      const node = chain.nodes.find(n => n.id === nodeId);
      return { node, comps };
    });

    panel.innerHTML = `
      <div class="panel-section">
        <div class="panel-title">🏢 公司穿透视图</div>
        <div style="font-size:11px;color:hsl(var(--text-muted));line-height:1.6;margin-bottom:8px">
          点击图谱节点查看关联上市公司。以下为全产业链公司概览：
        </div>
        ${allCompanies.map(({ node, comps }) => `
          <div style="margin-bottom:12px">
            <div style="font-size:12px;font-weight:600;color:hsl(var(--primary));margin-bottom:5px">${node?.label || nodeId}</div>
            ${comps.map(c => `
              <div class="company-detail-card">
                <div class="company-detail-header">
                  <span class="company-detail-name">${c.name}</span>
                  <span class="company-code">${c.code}</span>
                </div>
                <div class="company-metrics">
                  <div class="company-metric"><span class="company-metric-label">营收占比</span><span class="company-metric-value">${c.revPct}%</span></div>
                  <div class="company-metric"><span class="company-metric-label">自给率</span><span class="company-metric-value">${c.selfSuff}%</span></div>
                  <div class="company-metric"><span class="company-metric-label">海外业务</span><span class="company-metric-value">${c.overseas}%</span></div>
                  <div class="company-metric"><span class="company-metric-label">敏感度</span><span class="company-metric-value" style="color:${c.sensitivity > 0.8 ? 'hsl(var(--up))' : 'hsl(var(--text))'}">${(c.sensitivity*100).toFixed(0)}%</span></div>
                </div>
                <div style="font-size:10px;color:hsl(var(--text-dim));margin-top:4px">${c.biz}</div>
              </div>
            `).join('')}
          </div>
        `).join('')}
      </div>
    `;
    return;
  }

  // 选中节点的公司详情
  const node = chain.nodes.find(n => n.id === state.selectedNode);
  const companies = chain.companies[node.id] || [];

  panel.innerHTML = `
    <div class="panel-section">
      <div class="panel-title">🏢 ${node.label} — 关联公司</div>
      <div class="node-info-row"><span class="node-info-label">环节</span><span class="node-info-value">${node.sub}</span></div>
      <div class="node-info-row"><span class="node-info-label">定价权</span><span class="node-info-value">${node.pricingPower}/100</span></div>
      <div class="node-info-row"><span class="node-info-label">利润弹性</span><span class="node-info-value up">${node.profitElasticity}%</span></div>
    </div>
    ${companies.map(c => `
      <div class="panel-section">
        <div class="company-detail-card">
          <div class="company-detail-header">
            <span class="company-detail-name">${c.name} <span style="font-size:10px;color:hsl(var(--text-dim))">${c.biz}</span></span>
            <span class="company-tag">${c.code}</span>
          </div>
          <div class="company-metrics">
            <div class="company-metric"><span class="company-metric-label">该环节营收占比</span><span class="company-metric-value">${c.revPct}%</span></div>
            <div class="company-metric"><span class="company-metric-label">原材料自给率</span><span class="company-metric-value">${c.selfSuff}%</span></div>
            <div class="company-metric"><span class="company-metric-label">海外业务占比</span><span class="company-metric-value">${c.overseas}%</span></div>
            <div class="company-metric"><span class="company-metric-label">冲击敏感度</span><span class="company-metric-value" style="color:${c.sensitivity > 0.8 ? 'hsl(var(--up))' : 'hsl(var(--text))'}">${(c.sensitivity*100).toFixed(0)}%</span></div>
          </div>
          <div style="margin-top:8px">
            <div style="font-size:10px;color:hsl(var(--text-dim));margin-bottom:3px">冲击传导树</div>
            <div style="font-size:10px;color:hsl(var(--text-muted));line-height:1.5;font-family:var(--mono)">
              ⚡外部事件 → ${node.label}<br>
              &nbsp;&nbsp;↓ coeff=${(node.costSensitivity/100).toFixed(2)}<br>
              &nbsp;&nbsp;${c.name} (营收${c.revPct}%)<br>
              &nbsp;&nbsp;&nbsp;&nbsp;↓ 敏感度${(c.sensitivity*100).toFixed(0)}%<br>
              &nbsp;&nbsp;&nbsp;&nbsp;预估利润影响: <span style="color:hsl(var(--down))">−${(c.sensitivity * node.profitElasticity * 0.3).toFixed(1)}%</span>
            </div>
          </div>
        </div>
      </div>
    `).join('')}
    <div class="panel-section">
      <div class="ai-panel">
        <div class="ai-title">🤖 AI 选股分析</div>
        <div class="ai-content">基于 ${node.label} 环节的冲击推演，AI 将分析各公司的投资弹性，推荐受益标的并评估风险。</div>
        <button class="ai-btn" style="margin-top:8px" onclick="generateAIReport()">AI 选股分析</button>
      </div>
    </div>
  `;
}

function renderSimulationPanel() {
  const panel = el('rightPanel');
  const chain = INDUSTRY_CHAINS[state.currentChain];

  let impactSummary = '';
  if (state.selectedShock && state.simStep > 0) {
    const shock = SHOCK_EVENTS.find(s => s.id === state.selectedShock);
    const visited = simulateBFS(shock.target, state.simStep);
    const positive = Object.entries(visited).filter(([_, v]) => v === 'positive').map(([k]) => chain.nodes.find(n => n.id === k)?.label).filter(Boolean);
    const negative = Object.entries(visited).filter(([_, v]) => v === 'negative').map(([k]) => chain.nodes.find(n => n.id === k)?.label).filter(Boolean);

    impactSummary = `
      <div class="panel-section">
        <div class="panel-title">📊 推演结果 (T+${state.simStep}d)</div>
        ${positive.length ? `
          <div style="margin-bottom:8px">
            <div style="font-size:11px;color:hsl(var(--up));font-weight:600;margin-bottom:4px">✅ 受益环节 (${positive.length})</div>
            ${positive.map(p => `<div style="font-size:11px;color:hsl(var(--text));padding:2px 0">• ${p}</div>`).join('')}
          </div>
        ` : ''}
        ${negative.length ? `
          <div style="margin-bottom:8px">
            <div style="font-size:11px;color:hsl(var(--down));font-weight:600;margin-bottom:4px">⚠️ 受损环节 (${negative.length})</div>
            ${negative.map(p => `<div style="font-size:11px;color:hsl(var(--text));padding:2px 0">• ${p}</div>`).join('')}
          </div>
        ` : ''}
      </div>
      <div class="panel-section">
        <div class="panel-title">📝 冲击事件详情</div>
        <div class="node-info-row"><span class="node-info-label">事件</span><span class="node-info-value">${shock.name}</span></div>
        <div class="node-info-row"><span class="node-info-label">类别</span><span class="node-info-value">${shock.cat}</span></div>
        <div class="node-info-row"><span class="node-info-label">强度</span><span class="node-info-value">${shock.intensity}%</span></div>
        <div class="node-info-row"><span class="node-info-label">持续</span><span class="node-info-value">${shock.duration}d</span></div>
        <div style="font-size:11px;color:hsl(var(--text-muted));margin-top:6px;line-height:1.5">${shock.desc}</div>
      </div>
      ${shock.midVars ? `
      <div class="panel-section">
        <div class="panel-title">📈 中间传导变量</div>
        ${shock.midVars.map((mv, i) => {
          const activated = state.simStep >= (i+1)*3;
          return `<div class="node-info-row" style="opacity:${activated ? 1 : 0.4}">
            <span class="node-info-label">${mv.name} ${activated ? '✅' : '⏳'}</span>
            <span class="node-info-value ${mv.change.startsWith('+') ? 'up' : 'down'}">${mv.change}</span>
          </div>
          <div style="font-size:10px;color:hsl(var(--text-dim));margin-bottom:4px;opacity:${activated ? 1 : 0.4}">${mv.desc}</div>`;
        }).join('')}
      </div>` : ''}
      <div class="panel-section">
        <div class="ai-panel">
          <div class="ai-title">🤖 AI 冲击推演报告</div>
          <div class="ai-content">基于 ${shock.name} 的传导路径，AI 将生成完整的冲击影响分析，包括：</div>
          <div style="font-size:11px;color:hsl(var(--text-muted));margin-top:6px;line-height:1.6">
            • 冲击传导路径与时间序列<br>
            • 受益/受损环节量化评估<br>
            • 关联公司投资影响排序<br>
            • 历史相似事件复盘<br>
            • 策略建议与风险提示
          </div>
          <button class="ai-btn" style="margin-top:8px" onclick="generateAIReport()">生成推演报告</button>
        </div>
      </div>
    `;
  } else {
    impactSummary = `
      <div class="panel-section">
        <div class="panel-title">🎬 推演沙盘</div>
        <div style="font-size:12px;color:hsl(var(--text-muted));line-height:1.6">
          1. 从左侧选择或拖拽一个冲击事件<br>
          2. 调整冲击参数（强度/持续/衰减）<br>
          3. 点击"启动推演"<br>
          4. 使用时间轴回放传导过程
        </div>
      </div>
      <div class="panel-section">
        <div class="panel-title">⚡ 可选冲击事件</div>
        ${SHOCK_EVENTS.map(s => `
          <div class="shock-card ${state.selectedShock === s.id ? 'selected' : ''}" onclick="selectShock('${s.id}')">
            <span class="shock-tag ${s.cat}">${s.cat === 'policy' ? '政策' : s.cat === 'geo' ? '地缘' : s.cat === 'sentiment' ? '舆情' : '资金'}</span>
            <div class="shock-name">${s.name}</div>
            <div class="shock-desc">${s.desc}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  panel.innerHTML = impactSummary;
}

// ============================================================
//  事件处理
// ============================================================
async function selectChain(chainId) {
  state.currentChain = chainId;
  state.selectedNode = null;
  state.selectedShock = null;
  state.simStep = 0;
  await ensureChainLoaded(chainId);
  renderChainList();
  renderGraph();
  if (state.currentView === 'standard') renderRightPanel();
  else if (state.currentView === 'simulation') renderSimulationPanel();
  else renderCompanyView();
}

function switchView(view) {
  state.currentView = view;
  root.value.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  el('simControls').style.display = view === 'simulation' ? 'block' : 'none';
  el('timelineBar').style.display = view === 'simulation' ? 'flex' : 'none';
  el('shockSection').style.display = view === 'simulation' ? 'block' : 'none';
  el('layerSection').style.display = view === 'standard' ? 'block' : 'none';
  state.simStep = 0;

  renderGraph();
  if (view === 'standard') renderRightPanel();
  else if (view === 'simulation') renderSimulationPanel();
  else renderCompanyView();
}

function onNodeClick(nodeId) {
  state.selectedNode = nodeId;
  renderGraph();
  if (state.currentView === 'standard') renderRightPanel();
  else if (state.currentView === 'company') renderCompanyView();
  else renderSimulationPanel();
}

function onEdgeClick(idx) {
  const chain = INDUSTRY_CHAINS[state.currentChain];
  const edge = chain.edges[idx];
  const src = chain.nodes.find(n => n.id === edge.source);
  const tgt = chain.nodes.find(n => n.id === edge.target);
  alert(`${src?.label} → ${tgt?.label}\n类型: ${EDGE_LABELS[edge.type]}\n传导系数: ${edge.coeff}\n时滞: ${edge.lag}天\n\n${edge.desc}`);
}

function onCompanyClick(code) {
  alert(`跳转至 ${code} 行情页面（需对接现有行情模块）`);
}

function selectShock(shockId) {
  state.selectedShock = shockId;
  renderShockList();
  renderGraph();
  if (state.currentView === 'simulation') renderSimulationPanel();
}

function onShockDragStart(e, shockId) {
  state.selectedShock = shockId;
  e.dataTransfer.setData('text/plain', shockId);
  e.target.classList.add('dragging');
}

function onShockDragEnd(e) {
  e.target.classList.remove('dragging');
}

function toggleEdgeType(type, el) {
  state.edgeTypes[type] = !state.edgeTypes[type];
  el.classList.toggle('active', state.edgeTypes[type]);
  renderGraph();
}

function updateShockParam(key, val) {
  state.shockParams[key] = parseInt(val);
  if (key === 'intensity') el('intensityVal').textContent = val + '%';
  if (key === 'duration') el('durationVal').textContent = val + 'd';
  if (key === 'decay') el('decayVal').textContent = val + '%';
}

function runSimulation() {
  if (!state.selectedShock) {
    alert('请先选择一个冲击事件');
    return;
  }
  state.simStep = 0;
  state.simTotal = 20;
  renderTimelineTicks();
  playSimulation();
}

function playSimulation() {
  state.simPlaying = true;
  el('playBtn').textContent = '⏸';
  const interval = setInterval(() => {
    if (!state.simPlaying || state.simStep >= state.simTotal) {
      clearInterval(interval);
      state.simPlaying = false;
      el('playBtn').textContent = '▶';
      return;
    }
    state.simStep++;
    updateTimeline();
    renderGraph();
    renderSimulationPanel();
  }, 500);
  state._simInterval = interval;
}

function togglePlay() {
  if (state.simPlaying) {
    state.simPlaying = false;
    if (state._simInterval) clearInterval(state._simInterval);
    el('playBtn').textContent = '▶';
  } else {
    if (state.simStep >= state.simTotal) state.simStep = 0;
    playSimulation();
  }
}

function stepTimeline(delta) {
  state.simStep = Math.max(0, Math.min(state.simTotal, state.simStep + delta));
  updateTimeline();
  renderGraph();
  renderSimulationPanel();
}

function updateTimeline() {
  const pct = (state.simStep / state.simTotal) * 100;
  el('tlProgress').style.width = pct + '%';
  el('tlHandle').style.left = pct + '%';
  el('tlLabel').textContent = `T+${state.simStep}d`;
}

function renderTimelineTicks() {
  const ticks = [0, 5, 10, 15, 20];
  el('tlTicks').innerHTML = ticks.map(t =>
    `<div class="timeline-tick">T+${t}d</div>`
  ).join('');
}

function handleSearch(query) {
  if (!query) {
    renderGraph();
    return;
  }
  const chain = INDUSTRY_CHAINS[state.currentChain];
  const match = chain.nodes.find(n => n.label.includes(query) || n.sub.includes(query));
  if (match) {
    state.selectedNode = match.id;
    renderGraph();
    renderRightPanel();
  }
  // 搜索公司
  Object.entries(chain.companies).forEach(([nodeId, comps]) => {
    const found = comps.find(c => c.name.includes(query) || c.code.includes(query));
    if (found) {
      state.selectedNode = nodeId;
      renderGraph();
      if (state.currentView === 'company') renderCompanyView();
      else renderRightPanel();
    }
  });
}

function toggleLiquidity() {
  state.liquidityActive = !state.liquidityActive;
  el('liqOverlay').classList.toggle('active', state.liquidityActive);
  el('liqBtn').classList.toggle('primary');
  if (state.liquidityActive) {
    // 模拟资金面收紧效果
    const chain = INDUSTRY_CHAINS[state.currentChain];
    // 高资本开支行业加深标记
    renderGraph();
  } else {
    renderGraph();
  }
}

function toggleTheme() {
  const root = root.value;
  const isDark = !root.classList.contains('light');
  root.classList.toggle('light', isDark);
  el('themeBtn').textContent = isDark ? '☀️' : '🌙';
  renderGraph();
}

function switchInfoTab(tab, el) {
  root.value.querySelectorAll('.info-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  // 简化：重新渲染右侧
  renderRightPanel();
}

function generateAIReport() {
  const node = state.selectedNode ? INDUSTRY_CHAINS[state.currentChain].nodes.find(n => n.id === state.selectedNode) : null;
  const target = node ? node.label : INDUSTRY_CHAINS[state.currentChain].name;
  alert(`🤖 AI 报告生成中...\n\n目标: ${target}\n\n报告将包含：\n• 基本面分析\n• 传导逻辑解读\n• 投资弹性评估\n• 风险与催化剂\n\n（需对接豆包/DeepSeek API）`);
}

function zoomCanvas(factor) {
  state.zoom = Math.max(0.5, Math.min(2.5, state.zoom * factor));
  renderGraph();
}

function resetCanvas() {
  state.zoom = 1;
  renderGraph();
}

function fitCanvas() {
  state.zoom = 1;
  renderGraph();
}

function exportGraph() {
  alert('📷 图谱快照导出中...\n\n将导出为 PNG 图片 + Markdown 格式传导报告。\n（需对接后端导出接口）');
}

// ============================================================
//  初始化
// ============================================================

onMounted(async () => {
  bindWindow()
  try {
    const [listData, shockData] = await Promise.all([listIndustryChains(), listShocks()])
    const items = (listData && listData.items) || []
    INDUSTRY_CHAINS = {}
    items.forEach((it) => {
      INDUSTRY_CHAINS[it.id] = {
        id: it.id, name: it.name, icon: it.icon, color: it.color,
        category: it.category, summary: it.summary, source: it.source, nodeCount: it.nodeCount,
      }
    })
    SHOCK_EVENTS = (shockData && shockData.items) || []
  } catch (e) {
    console.error('[ics] 加载产业链数据失败', e)
  }
  renderShockList()
  renderTimelineTicks()
  const firstId = Object.keys(INDUSTRY_CHAINS)[0]
  if (firstId) {
    try { await selectChain(firstId) } catch (e) { console.error(e) }
  }
})

onUnmounted(() => {
  unbindWindow()
  if (state && state._simInterval) clearInterval(state._simInterval)
})

</script>

<style>
.ics-sandbox { height: calc(100vh - 160px); min-height: 560px; display: flex; flex-direction: column; }

/* ========== 设计令牌（对齐项目 HSL 系统） ========== */
.ics-sandbox {
  --bg: 228 35% 7%;
  --bg-elevated: 225 28% 11%;
  --bg-card: 224 25% 13%;
  --bg-hover: 222 25% 16%;
  --border: 220 20% 20%;
  --border-strong: 220 20% 28%;
  --text: 210 20% 92%;
  --text-muted: 215 16% 60%;
  --text-dim: 215 14% 45%;
  --primary: 190 100% 50%;
  --up: 0 88% 64%;
  --down: 149 100% 44%;
  --warn: 38 100% 55%;
  --danger: 0 80% 55%;
  --cost: 220 80% 65%;
  --demand: 175 80% 50%;
  --subst: 30 90% 55%;
  --supply: 0 75% 55%;
  --radius: 0.5rem;
  --font: 'Inter', -apple-system, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
}
.ics-sandbox.light {
  --bg: 210 20% 98%;
  --bg-elevated: 0 0% 100%;
  --bg-card: 210 20% 96%;
  --bg-hover: 210 20% 92%;
  --border: 215 16% 85%;
  --border-strong: 215 16% 70%;
  --text: 222 30% 15%;
  --text-muted: 215 16% 42%;
  --text-dim: 215 14% 55%;
  --primary: 190 90% 40%;
  --up: 0 75% 50%;
  --down: 149 70% 35%;
  --cost: 220 70% 55%;
  --demand: 175 70% 40%;
  --subst: 30 80% 50%;
  --supply: 0 65% 50%;
}
.ics-sandbox * { margin: 0; padding: 0; box-sizing: border-box; }
.ics-sandbox { font-family: var(--font); background: hsl(var(--bg)); color: hsl(var(--text)); overflow: hidden; height: 100%; }
.ics-sandbox .mono { font-family: var(--mono); }

/* ========== 布局 ========== */
.ics-sandbox .app { display: flex; flex-direction: column; height: 100%; }
.ics-sandbox .header {
  height: 52px; display: flex; align-items: center; gap: 12px; padding: 0 16px;
  background: hsl(var(--bg-elevated)); border-bottom: 1px solid hsl(var(--border));
  flex-shrink: 0; z-index: 100;
}
.ics-sandbox .logo { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; white-space: nowrap; }
.ics-sandbox .logo-icon { width: 28px; height: 28px; border-radius: 6px; background: linear-gradient(135deg, hsl(var(--primary)), hsl(190 80% 40%)); display: flex; align-items: center; justify-content: center; font-size: 14px; }

.ics-sandbox .view-switcher { display: flex; gap: 2px; background: hsl(var(--bg-card)); border-radius: 8px; padding: 3px; }
.ics-sandbox .view-btn { padding: 6px 14px; border: none; background: none; color: hsl(var(--text-muted)); font-size: 12px; cursor: pointer; border-radius: 6px; transition: all 0.2s; font-family: var(--font); display: flex; align-items: center; gap: 5px; white-space: nowrap; }
.ics-sandbox .view-btn.active { background: hsl(var(--primary) / 0.15); color: hsl(var(--primary)); }
.ics-sandbox .view-btn:hover:not(.active) { color: hsl(var(--text)); }

.ics-sandbox .header-spacer { flex: 1; }
.ics-sandbox .header-btn { padding: 6px 12px; border: 1px solid hsl(var(--border-strong)); background: hsl(var(--bg-card)); color: hsl(var(--text)); font-size: 12px; cursor: pointer; border-radius: 6px; transition: all 0.2s; font-family: var(--font); display: flex; align-items: center; gap: 5px; white-space: nowrap; }
.ics-sandbox .header-btn:hover { background: hsl(var(--bg-hover)); border-color: hsl(var(--primary) / 0.5); }
.ics-sandbox .header-btn.primary { background: hsl(var(--primary) / 0.15); border-color: hsl(var(--primary) / 0.4); color: hsl(var(--primary)); }

.ics-sandbox .search-box { display: flex; align-items: center; gap: 6px; background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); border-radius: 6px; padding: 4px 10px; }
.ics-sandbox .search-box input { background: none; border: none; color: hsl(var(--text)); font-size: 12px; outline: none; font-family: var(--font); width: 140px; }

.ics-sandbox .main { display: flex; flex: 1; height: 0; }
.ics-sandbox .left-panel { width: 240px; background: hsl(var(--bg-elevated)); border-right: 1px solid hsl(var(--border)); overflow-y: auto; flex-shrink: 0; }
.ics-sandbox .center-area { flex: 1; min-width: 0; overflow: hidden; position: relative; display: flex; flex-direction: column; }
.ics-sandbox .right-panel { width: 340px; background: hsl(var(--bg-elevated)); border-left: 1px solid hsl(var(--border)); overflow-y: auto; flex-shrink: 0; }

.ics-sandbox .panel-section { padding: 12px 14px; border-bottom: 1px solid hsl(var(--border)); }
.ics-sandbox .panel-title { font-size: 11px; font-weight: 600; color: hsl(var(--text-muted)); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 5px; }

/* 产业链目录 */
.ics-sandbox .chain-item { padding: 8px 10px; background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); border-radius: var(--radius); margin-bottom: 6px; cursor: pointer; transition: all 0.2s; font-size: 12px; display: flex; align-items: center; gap: 8px; }
.ics-sandbox .chain-item:hover { background: hsl(var(--bg-hover)); border-color: hsl(var(--primary) / 0.4); }
.ics-sandbox .chain-item.active { border-color: hsl(var(--primary)); background: hsl(var(--primary) / 0.08); color: hsl(var(--primary)); }
.ics-sandbox .chain-icon { width: 20px; height: 20px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }

/* 冲击事件卡片 */
.ics-sandbox .shock-card { padding: 9px 11px; background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); border-radius: var(--radius); margin-bottom: 6px; cursor: grab; transition: all 0.2s; position: relative; overflow: hidden; }
.ics-sandbox .shock-card:hover { background: hsl(var(--bg-hover)); border-color: hsl(var(--warn) / 0.4); transform: translateX(2px); }
.ics-sandbox .shock-card.dragging { opacity: 0.5; cursor: grabbing; }
.ics-sandbox .shock-card.selected { border-color: hsl(var(--warn)); background: hsl(var(--warn) / 0.08); }
.ics-sandbox .shock-tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; margin-bottom: 4px; font-weight: 600; }
.ics-sandbox .shock-tag.policy { background: hsl(220 80% 50% / 0.2); color: hsl(220 80% 70%); }
.ics-sandbox .shock-tag.geo { background: hsl(0 80% 50% / 0.2); color: hsl(0 80% 70%); }
.ics-sandbox .shock-tag.sentiment { background: hsl(38 100% 50% / 0.2); color: hsl(38 100% 65%); }
.ics-sandbox .shock-tag.liquidity { background: hsl(280 80% 50% / 0.2); color: hsl(280 80% 70%); }
.ics-sandbox .shock-name { font-size: 12px; font-weight: 500; margin-bottom: 2px; }
.ics-sandbox .shock-desc { font-size: 11px; color: hsl(var(--text-dim)); line-height: 1.4; }
.ics-sandbox .shock-intensity { display: flex; align-items: center; gap: 4px; margin-top: 4px; }
.ics-sandbox .intensity-bar { width: 60px; height: 4px; background: hsl(var(--bg-hover)); border-radius: 2px; overflow: hidden; }
.ics-sandbox .intensity-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }

/* 图谱画布 */
.ics-sandbox .canvas-container { flex: 1; overflow: auto; position: relative; background: hsl(var(--bg)); }
.ics-sandbox .canvas-toolbar { position: absolute; top: 10px; right: 10px; display: flex; gap: 4px; z-index: 10; }
.ics-sandbox .canvas-btn { width: 30px; height: 30px; background: hsl(var(--bg-elevated)); border: 1px solid hsl(var(--border)); border-radius: 6px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: hsl(var(--text-muted)); font-size: 14px; transition: all 0.2s; }
.ics-sandbox .canvas-btn:hover { background: hsl(var(--bg-hover)); color: hsl(var(--primary)); border-color: hsl(var(--primary) / 0.4); }

.ics-sandbox #graphSvg { display: block; }

/* 图层开关 */
.ics-sandbox .layer-toggles { display: flex; flex-wrap: wrap; gap: 4px; }
.ics-sandbox .layer-chip { font-size: 10px; padding: 3px 8px; border-radius: 4px; background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); cursor: pointer; transition: all 0.2s; color: hsl(var(--text-dim)); user-select: none; }
.ics-sandbox .layer-chip.active { color: hsl(var(--text)); border-color: hsl(var(--border-strong)); }
.ics-sandbox .layer-chip.cost.active { background: hsl(var(--cost) / 0.15); border-color: hsl(var(--cost) / 0.5); color: hsl(var(--cost)); }
.ics-sandbox .layer-chip.demand.active { background: hsl(var(--demand) / 0.15); border-color: hsl(var(--demand) / 0.5); color: hsl(var(--demand)); }
.ics-sandbox .layer-chip.subst.active { background: hsl(var(--subst) / 0.15); border-color: hsl(var(--subst) / 0.5); color: hsl(var(--subst)); }
.ics-sandbox .layer-chip.supply.active { background: hsl(var(--supply) / 0.15); border-color: hsl(var(--supply) / 0.5); color: hsl(var(--supply)); }

/* 时间轴 */
.ics-sandbox .timeline-bar { height: 56px; background: hsl(var(--bg-elevated)); border-top: 1px solid hsl(var(--border)); display: flex; align-items: center; padding: 0 16px; gap: 12px; flex-shrink: 0; }
.ics-sandbox .timeline-track { flex: 1; height: 32px; position: relative; }
.ics-sandbox .timeline-rail { position: absolute; top: 50%; left: 0; right: 0; height: 4px; background: hsl(var(--bg-card)); border-radius: 2px; transform: translateY(-50%); }
.ics-sandbox .timeline-progress { position: absolute; top: 50%; left: 0; height: 4px; background: hsl(var(--primary)); border-radius: 2px; transform: translateY(-50%); transition: width 0.3s; }
.ics-sandbox .timeline-handle { position: absolute; top: 50%; width: 14px; height: 14px; background: hsl(var(--primary)); border: 2px solid hsl(var(--bg-elevated)); border-radius: 50%; transform: translate(-50%, -50%); cursor: grab; box-shadow: 0 0 0 4px hsl(var(--primary) / 0.2); transition: left 0.3s; }
.ics-sandbox .timeline-ticks { position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; align-items: center; pointer-events: none; }
.ics-sandbox .timeline-tick { font-size: 10px; color: hsl(var(--text-dim)); font-family: var(--mono); }
.ics-sandbox .timeline-btn { width: 32px; height: 32px; border: 1px solid hsl(var(--border-strong)); background: hsl(var(--bg-card)); color: hsl(var(--text)); border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 12px; transition: all 0.2s; }
.ics-sandbox .timeline-btn:hover { background: hsl(var(--bg-hover)); }
.ics-sandbox .timeline-btn.play { background: hsl(var(--primary) / 0.15); border-color: hsl(var(--primary) / 0.4); color: hsl(var(--primary)); }
.ics-sandbox .timeline-label { font-size: 11px; color: hsl(var(--text-muted)); font-family: var(--mono); white-space: nowrap; }

/* 右侧面板内容 */
.ics-sandbox .info-tabs { display: flex; gap: 1px; background: hsl(var(--border)); margin: -12px -14px 10px; }
.ics-sandbox .info-tab { flex: 1; padding: 8px; text-align: center; font-size: 11px; cursor: pointer; background: hsl(var(--bg-elevated)); color: hsl(var(--text-muted)); transition: all 0.2s; border-bottom: 2px solid transparent; }
.ics-sandbox .info-tab.active { color: hsl(var(--primary)); border-bottom-color: hsl(var(--primary)); background: hsl(var(--bg-elevated)); }

.ics-sandbox .node-info-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; font-size: 12px; border-bottom: 1px solid hsl(var(--border) / 0.5); }
.ics-sandbox .node-info-label { color: hsl(var(--text-muted)); }
.ics-sandbox .node-info-value { color: hsl(var(--text)); font-family: var(--mono); font-size: 12px; }
.ics-sandbox .node-info-value.up { color: hsl(var(--up)); }
.ics-sandbox .node-info-value.down { color: hsl(var(--down)); }

.ics-sandbox .company-row { padding: 8px 10px; background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); border-radius: var(--radius); margin-bottom: 5px; cursor: pointer; transition: all 0.2s; }
.ics-sandbox .company-row:hover { background: hsl(var(--bg-hover)); border-color: hsl(var(--primary) / 0.4); }
.ics-sandbox .company-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
.ics-sandbox .company-name { font-size: 12px; font-weight: 600; }
.ics-sandbox .company-code { font-size: 10px; color: hsl(var(--text-dim)); font-family: var(--mono); }
.ics-sandbox .company-meta { display: flex; gap: 10px; font-size: 10px; color: hsl(var(--text-muted)); }
.ics-sandbox .sensitivity-bar { width: 50px; height: 3px; background: hsl(var(--bg-hover)); border-radius: 2px; overflow: hidden; }
.ics-sandbox .sensitivity-fill { height: 100%; border-radius: 2px; }

.ics-sandbox .news-item { padding: 7px 0; border-bottom: 1px solid hsl(var(--border) / 0.5); font-size: 11px; }
.ics-sandbox .news-time { color: hsl(var(--text-dim)); font-family: var(--mono); font-size: 10px; }
.ics-sandbox .news-title { color: hsl(var(--text)); margin-top: 2px; line-height: 1.4; }

.ics-sandbox .ai-panel { background: hsl(var(--primary) / 0.05); border: 1px solid hsl(var(--primary) / 0.2); border-radius: var(--radius); padding: 12px; margin-top: 10px; }
.ics-sandbox .ai-title { font-size: 12px; font-weight: 600; color: hsl(var(--primary)); margin-bottom: 6px; display: flex; align-items: center; gap: 5px; }
.ics-sandbox .ai-content { font-size: 11px; color: hsl(var(--text-muted)); line-height: 1.6; }
.ics-sandbox .ai-btn { width: 100%; padding: 8px; background: hsl(var(--primary) / 0.15); border: 1px solid hsl(var(--primary) / 0.4); color: hsl(var(--primary)); border-radius: 6px; cursor: pointer; font-size: 12px; font-family: var(--font); transition: all 0.2s; }
.ics-sandbox .ai-btn:hover { background: hsl(var(--primary) / 0.25); }

/* 中间变量浮窗 */
.ics-sandbox .midvar-popup {
  position: absolute; background: hsl(var(--bg-elevated)); border: 1px solid hsl(var(--warn) / 0.5);
  border-radius: 8px; padding: 8px 12px; font-size: 11px; pointer-events: none; z-index: 50;
  box-shadow: 0 4px 16px hsl(0 0% 0% / 0.4); max-width: 200px; transition: opacity 0.3s;
}
.ics-sandbox .midvar-title { font-weight: 600; color: hsl(var(--warn)); margin-bottom: 3px; font-size: 11px; }
.ics-sandbox .midvar-desc { color: hsl(var(--text-muted)); line-height: 1.4; }
.ics-sandbox .midvar-value { color: hsl(var(--up)); font-family: var(--mono); font-weight: 600; }

/* 图例 */
.ics-sandbox .legend { position: absolute; bottom: 10px; left: 10px; background: hsl(var(--bg-elevated) / 0.9); border: 1px solid hsl(var(--border)); border-radius: 8px; padding: 8px 12px; font-size: 11px; z-index: 5; backdrop-filter: blur(8px); }
.ics-sandbox .legend-title { font-weight: 600; color: hsl(var(--text-muted)); margin-bottom: 5px; font-size: 10px; text-transform: uppercase; }
.ics-sandbox .legend-item { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.ics-sandbox .legend-line { width: 24px; height: 2px; border-radius: 1px; }
.ics-sandbox .legend-node { width: 14px; height: 10px; border-radius: 3px; }

/* 冲击控制面板 */
.ics-sandbox .shock-controls { background: hsl(var(--warn) / 0.05); border: 1px solid hsl(var(--warn) / 0.2); border-radius: var(--radius); padding: 10px; margin-bottom: 10px; }
.ics-sandbox .shock-control-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ics-sandbox .shock-control-label { font-size: 11px; color: hsl(var(--text-muted)); white-space: nowrap; min-width: 50px; }
.ics-sandbox .shock-slider { flex: 1; -webkit-appearance: none; height: 4px; background: hsl(var(--bg-hover)); border-radius: 2px; outline: none; }
.ics-sandbox .shock-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 14px; height: 14px; background: hsl(var(--warn)); border-radius: 50%; cursor: pointer; }
.ics-sandbox .shock-value { font-size: 11px; color: hsl(var(--warn)); font-family: var(--mono); min-width: 32px; text-align: right; }

/* 流动光效 */
@keyframes flowDash { to { stroke-dashoffset: -20; } }
.ics-sandbox .flow-line { stroke-dasharray: 6 4; animation: flowDash 0.8s linear infinite; }

@keyframes pulseGlow { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
.ics-sandbox .pulse-node { animation: pulseGlow 1.2s ease-in-out infinite; }

@keyframes ripple { 0% { r: 0; opacity: 0.6; } 100% { r: 40; opacity: 0; } }
.ics-sandbox .ripple-circle { animation: ripple 1s ease-out; }

/* 主题切换 */
.ics-sandbox .theme-toggle { width: 30px; height: 30px; border: 1px solid hsl(var(--border-strong)); background: hsl(var(--bg-card)); color: hsl(var(--text-muted)); border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; transition: all 0.2s; }
.ics-sandbox .theme-toggle:hover { color: hsl(var(--primary)); border-color: hsl(var(--primary) / 0.4); }

/* 滚动条 */
.ics-sandbox ::-webkit-scrollbar { width: 5px; height: 5px; }
.ics-sandbox ::-webkit-scrollbar-track { background: transparent; }
.ics-sandbox ::-webkit-scrollbar-thumb { background: hsl(var(--border-strong)); border-radius: 3px; }
.ics-sandbox ::-webkit-scrollbar-thumb:hover { background: hsl(var(--text-dim)); }

/* 公司穿透视图 */
.ics-sandbox .company-detail-card { background: hsl(var(--bg-card)); border: 1px solid hsl(var(--border)); border-radius: var(--radius); padding: 10px; margin-bottom: 8px; }
.ics-sandbox .company-detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.ics-sandbox .company-detail-name { font-size: 13px; font-weight: 700; }
.ics-sandbox .company-tag { font-size: 10px; padding: 2px 6px; border-radius: 3px; background: hsl(var(--primary) / 0.15); color: hsl(var(--primary)); }
.ics-sandbox .company-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; }
.ics-sandbox .company-metric { display: flex; justify-content: space-between; font-size: 10px; }
.ics-sandbox .company-metric-label { color: hsl(var(--text-dim)); }
.ics-sandbox .company-metric-value { color: hsl(var(--text)); font-family: var(--mono); }

/* SVG 节点样式 */
.ics-sandbox .node-rect { cursor: pointer; transition: all 0.2s; }
.ics-sandbox .node-rect:hover { filter: brightness(1.2); }
.ics-sandbox .node-circle { cursor: pointer; transition: all 0.2s; }
.ics-sandbox .node-circle:hover { filter: brightness(1.2); }
.ics-sandbox .edge-line { transition: all 0.3s; pointer-events: stroke; cursor: pointer; }
.ics-sandbox .edge-label { font-size: 9px; fill: hsl(var(--text-dim)); pointer-events: none; font-family: var(--mono); }
.ics-sandbox .node-label { font-size: 11px; fill: hsl(var(--text)); pointer-events: none; font-weight: 500; }
.ics-sandbox .node-sublabel { font-size: 9px; fill: hsl(var(--text-muted)); pointer-events: none; font-family: var(--mono); }

.ics-sandbox .dimmed { opacity: 0.2; }
.ics-sandbox .highlighted { opacity: 1; }

/* 资金面全局图层 */
.ics-sandbox .liquidity-overlay { position: absolute; inset: 0; pointer-events: none; z-index: 1; transition: opacity 0.5s; }
.ics-sandbox .liquidity-overlay.active { opacity: 1; background: radial-gradient(ellipse at center, transparent 30%, hsl(280 80% 30% / 0.15) 100%); }

</style>

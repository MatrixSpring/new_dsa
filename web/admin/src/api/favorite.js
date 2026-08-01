import request from './request'

/** 获取自选股列表 */
export function getFavoriteList() {
  return request.get('/api/v1/favorite/list')
}

/** 添加自选股 (参数走 Query) */
export function addFavorite(code, name = '') {
  return request.post('/api/v1/favorite/add', null, { params: { code, name } })
}

/** 删除自选股 (参数走 Query) */
export function deleteFavorite(favId) {
  return request.delete('/api/v1/favorite/delete', { params: { fav_id: favId } })
}

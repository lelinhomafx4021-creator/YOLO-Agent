import { get } from './client.js'

export function getRuntime() {
  return get('/system/runtime')
}

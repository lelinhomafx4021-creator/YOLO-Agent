/**
 * useAnnotationKeyboard - 标注键盘快捷键组合式函数
 *
 * 功能描述：
 * 为标注页面提供全局键盘快捷键支持。通过监听 window 的 keydown 事件，
 * 将按键映射到标注操作（上一张/下一张图片、切换绘制/选择模式、
 * 删除选框、取消选中、设置类别、保存等）。
 * 组件挂载时注册事件，卸载时自动移除，避免内存泄漏。
 *
 * 使用方式：
 *   import { useAnnotationKeyboard } from '@/composables/useAnnotationKeyboard'
 *
 *   useAnnotationKeyboard({
 *     onPrevImage:  () => store.prevImage(),
 *     onNextImage:  () => store.nextImage(),
 *     onSave:       () => store.save(),
 *     onToggleMode: (mode) => store.setMode(mode),
 *     onSetClass:   (id) => store.setClass(id),
 *     onDeleteBox:  () => store.deleteSelectedBox(),
 *     onDeselect:   () => store.deselect(),
 *   })
 */

// ---------------------------------------------------------------------------
// Vue 生命周期钩子：onMounted（挂载后）和 onUnmounted（卸载前）
// ---------------------------------------------------------------------------
import { onMounted, onUnmounted } from 'vue'

/**
 * 导出组合式函数
 *
 * 该函数接收一个 handlers 对象，其中包含各类标注操作的回调函数。
 * 在组件挂载时注册键盘事件监听，在组件卸载时自动移除监听。
 * 通过解耦按键映射与具体业务逻辑，使得该组合式函数可以被任何标注相关组件复用。
 *
 * @param {Object}   handlers               - 回调函数集合，每种按键操作对应的处理函数
 * @param {Function} handlers.onPrevImage   - 上一张图片回调（按 A 或左方向键）
 * @param {Function} handlers.onNextImage   - 下一张图片回调（按 D 或右方向键）
 * @param {Function} handlers.onSave        - 保存回调（按 Ctrl+S / Cmd+S）
 * @param {Function} handlers.onToggleMode  - 切换标注模式回调，接收模式名称 'draw'|'select'
 * @param {Function} handlers.onSetClass    - 设置类别回调，接收类别 ID (0-9)
 * @param {Function} handlers.onDeleteBox   - 删除当前选框回调（按 Delete / Backspace）
 * @param {Function} handlers.onDeselect    - 取消选中回调（按 Escape）
 */
export function useAnnotationKeyboard(handlers) {
  // ---------------------------------------------------------------------------
  // 响应式变量 / 状态
  // ---------------------------------------------------------------------------
  // 此组合式函数不定义自己的响应式状态，所有状态由调用方管理。
  // handlers 中传入的回调函数即为与外部状态交互的接口。
  // 这种设计使得组合式函数保持纯逻辑，不耦合任何具体状态管理实现。

  // ---------------------------------------------------------------------------
  // 解构回调函数
  // ---------------------------------------------------------------------------
  // 将 handlers 对象中的回调函数逐一解构为局部变量，使后续 handleKeydown
  // 中的调用更加简洁。每一行标注了函数的签名类型，便于理解参数和返回值。
  const {
    onPrevImage,      // () => void —— 切换到上一张图片
    onNextImage,      // () => void —— 切换到下一张图片
    onSave,           // () => void —— 保存当前标注
    onToggleMode,     // (mode: string) => void —— 切换标注模式（'draw' | 'select'）
    onSetClass,       // (classId: number) => void —— 设置标注类别（0-9）
    onDeleteBox,      // () => void —— 删除当前选中的标注框
    onDeselect,       // () => void —— 取消当前选中状态
  } = handlers

  /**
   * keyboard 事件处理函数
   *
   * 核心逻辑：根据按下的键名匹配到对应的标注操作并执行回调。
   * 当焦点在输入框（INPUT）、下拉框（SELECT）或文本域（TEXTAREA）中时，
   * 不拦截按键事件，以保证表单控件的正常输入行为。
   *
   * 对于可能触发浏览器默认行为的按键（如 ArrowLeft/ArrowRight 滚动页面、
   * Backspace 回退、S 键保存页面等），通过 e.preventDefault() 阻止默认行为，
   * 确保快捷键操作不会引发意外的页面导航或表单提交。
   *
   * 按键映射表：
   *   A / ArrowLeft    -> 上一张图片
   *   D / ArrowRight   -> 下一张图片
   *   B                -> 切换为绘制（draw）模式
   *   V                -> 切换为选择（select）模式
   *   Delete / Backspace -> 删除当前选框
   *   Escape           -> 取消选中
   *   S（+Ctrl/Meta）   -> 保存
   *   0-9              -> 设置对应编号的类别
   */
  function handleKeydown(e) {
    // 表单控件焦点检测：当用户正在输入框中编辑时，不处理任何快捷键
    const tagName = e.target.tagName
    if (tagName === 'INPUT' || tagName === 'SELECT' || tagName === 'TEXTAREA') return

    // 将按键名统一转为小写后匹配，保证大小写不敏感的按键识别
    switch (e.key.toLowerCase()) {
      // ---------- 导航操作 ----------
      // A 键或左方向键：切换到上一张图片
      case 'a':
      case 'arrowleft':
        e.preventDefault()   // 阻止浏览器默认的左方向键滚动行为
        onPrevImage?.()      // 可选链调用，即使回调未传入也不会报错
        break

      // D 键或右方向键：切换到下一张图片
      case 'd':
      case 'arrowright':
        e.preventDefault()   // 阻止浏览器默认的右方向键滚动行为
        onNextImage?.()
        break

      // ---------- 模式切换 ----------
      // B 键：切换为绘制（画框）模式，用于在图片上绘制新的标注框
      case 'b':
        e.preventDefault()   // 阻止可能触发的浏览器快捷键
        onToggleMode?.('draw')
        break

      // V 键：切换为选择（移动/编辑）模式，用于选取已有标注框进行调整
      case 'v':
        e.preventDefault()
        onToggleMode?.('select')
        break

      // ---------- 编辑操作 ----------
      // Delete 或 Backspace：删除当前选中的标注框
      case 'delete':
      case 'backspace':
        e.preventDefault()   // 阻止 Backspace 触发的浏览器页面回退
        onDeleteBox?.()
        break

      // Escape：取消当前选中状态，清空选框的高亮或激活状态
      case 'escape':
        e.preventDefault()
        onDeselect?.()
        break

      // ---------- 保存操作 ----------
      // S 键需同时按住 Ctrl（Windows/Linux）或 Command（macOS）才触发保存
      case 's':
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault() // 阻止浏览器默认的"另存为"对话框
          onSave?.()
        }
        break

      // ---------- 类别快速选择 ----------
      // 数字键 0-9：快速为当前标注设置类别，无需鼠标操作下拉框
      // 例如按 1 选择类别 ID 为 1 的标注类别
      case '0': case '1': case '2': case '3': case '4':
      case '5': case '6': case '7': case '8': case '9':
        onSetClass?.(parseInt(e.key))
        break

      // 未匹配到任何已定义快捷键的按键，不做任何处理
    }
  }

  // ---------------------------------------------------------------------------
  // 生命周期钩子
  // ---------------------------------------------------------------------------

  // 组件挂载完成时：在全局 window 对象上注册 keydown 事件监听
  // 使用全局监听而非组件内监听，确保在任何焦点状态下都能响应快捷键
  onMounted(() => window.addEventListener('keydown', handleKeydown))

  // 组件卸载前：移除已注册的 keydown 事件监听
  // 这是必要的清理操作，防止组件销毁后事件监听仍然残留，导致内存泄漏
  // 或在已卸载的组件上意外触发回调
  onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
}

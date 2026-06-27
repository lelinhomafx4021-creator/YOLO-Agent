<template>
  <ConfirmDialog
    :visible="confirmDialog.visible"
    :title="confirmDialog.title"
    :message="confirmDialog.message"
    @confirm="confirmDialog.onConfirm()"
    @cancel="confirmDialog.visible = false"
  />
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>项目工作台</h1>
        <p>围绕项目发起训练、测试和 Agent 分析，数据直接从数据集列表自由选择。</p>
      </div>
      <div class="header-actions">
        <button class="primary-action" @click="showCreate = true"><AppIcon name="add" /> 新建项目</button>
      </div>
    </div>

    <div v-if="loading" class="project-grid compact-project-grid">
      <div class="project-card compact-project-card skeleton skeleton-card"></div>
      <div class="project-card compact-project-card skeleton skeleton-card"></div>
      <div class="project-card compact-project-card skeleton skeleton-card"></div>
    </div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <div v-else-if="projects.length === 0" class="empty-state compact-empty">
      <strong>还没有项目</strong>
      <span>创建一个项目来组织训练、测试和模型管理。</span>
      <button class="primary-action" @click="showCreate = true">创建第一个项目</button>
    </div>

    <div v-else class="project-grid compact-project-grid">
      <RouterLink
        v-for="project in projects"
        :key="project.id"
        class="project-card compact-project-card"
        :to="`/projects/${project.id}`"
        @click="setActiveProjectContext(project)"
      >
        <button class="card-edit-btn" title="编辑项目" @click.prevent.stop="startEdit(project)">✎</button>
        <button class="card-delete-btn" title="删除项目" @click.prevent.stop="confirmDelete(project)">×</button>
        <div class="project-card-head">
          <div>
            <strong>{{ project.name }}</strong>
            <span>{{ project.description || '暂无说明' }}</span>
          </div>
          <i>{{ project.task_type || 'detect' }}</i>
        </div>
        <div class="project-card-stats">
          <div><span>数据</span><b>{{ project.dataset_count || 0 }}</b></div>
          <div><span>训练</span><b>{{ project.training_count || 0 }}</b></div>
          <div><span>测试</span><b>{{ project.evaluation_count || 0 }}</b></div>
          <div><span>模型</span><b>{{ project.model_count || 0 }}</b></div>
        </div>
        <div class="project-card-foot">
          <span>最佳 mAP50：{{ fmtMetric(project.best_map50) }}</span>
          <span>{{ shortTime(project.updated_at || project.created_at) }}</span>
        </div>
      </RouterLink>
    </div>

    <div v-if="showCreate" class="dialog-overlay" @click.self="showCreate = false">
      <div class="dialog">
        <h3>新建项目</h3>
        <label>项目名称 <input v-model="form.name" placeholder="例如：安全帽检测项目" /></label>
        <label>项目说明 <input v-model="form.description" placeholder="说明业务场景、数据来源或目标指标" /></label>
        <label>任务类型
          <select v-model="form.task_type">
            <option value="detect">目标检测 detect</option>
          </select>
        </label>
        <div class="dialog-actions">
          <button class="secondary-action" @click="showCreate = false">取消</button>
          <button class="primary-action" @click="submit">创建</button>
        </div>
        <p v-if="dialogError" class="error">{{ dialogError }}</p>
      </div>
    </div>

    <div v-if="showEdit" class="dialog-overlay" @click.self="showEdit = false">
      <div class="dialog">
        <h3>编辑项目</h3>
        <label>项目名称 <input v-model="editForm.name" placeholder="项目名称" /></label>
        <label>项目说明 <input v-model="editForm.description" placeholder="项目说明" /></label>
        <div class="dialog-actions">
          <button class="secondary-action" @click="showEdit = false">取消</button>
          <button class="primary-action" @click="saveEdit">保存</button>
        </div>
        <p v-if="editError" class="error">{{ editError }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { createProject, deleteProject, listProjects, updateProject } from '../api/projects.js'
import { setActiveProjectContext } from '../state/projectContext.js'

const projects = ref([])
const loading = ref(true)
const error = ref('')
const dialogError = ref('')
const showCreate = ref(false)
const showEdit = ref(false)
const editError = ref('')
const editingProject = ref(null)
const editForm = reactive({ name: '', description: '' })
const form = reactive({ name: '', description: '', task_type: 'detect' })

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    projects.value = await listProjects()
  } catch (err) {
    error.value = err?.message || '项目加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  dialogError.value = ''
  if (!form.name.trim()) {
    dialogError.value = '项目名称不能为空'
    return
  }
  try {
    const project = await createProject({ ...form, name: form.name.trim() })
    setActiveProjectContext(project)
    showCreate.value = false
    form.name = ''
    form.description = ''
    await load()
  } catch (err) {
    dialogError.value = err?.message || '创建项目失败'
  }
}

const confirmDialog = reactive({ visible: false, title: '', message: '', onConfirm: () => {} })

function confirmDelete(project) {
  confirmDialog.title = '删除项目'
  confirmDialog.message = `确认删除项目「${project.name}」？所有关联的训练、模型、评估记录都会被永久删除。`
  confirmDialog.onConfirm = async () => {
    confirmDialog.visible = false
    try {
      await deleteProject(project.id)
      await load()
    } catch (err) {
      alert(err?.message || '删除项目失败')
    }
  }
  confirmDialog.visible = true
}

function startEdit(project) {
  editingProject.value = project
  editForm.name = project.name || ''
  editForm.description = project.description || ''
  editError.value = ''
  showEdit.value = true
}

async function saveEdit() {
  if (!editingProject.value) return
  editError.value = ''
  try {
    await updateProject(editingProject.value.id, { name: editForm.name.trim(), description: editForm.description.trim() })
    showEdit.value = false
    await load()
  } catch (err) {
    editError.value = err?.message || '保存失败'
  }
}

function fmtMetric(value) {
  return value === null || value === undefined ? '-' : Number(value).toFixed(3)
}

function shortTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
}
</script>

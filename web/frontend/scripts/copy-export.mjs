import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(here, '..')
const projectRoot = resolve(frontendRoot, '..', '..')
const source = resolve(frontendRoot, 'out')
const target = resolve(projectRoot, 'pages', 'moirai')

if (!existsSync(source)) {
  console.error(`Next export output not found: ${source}`)
  process.exit(1)
}

rmSync(target, { recursive: true, force: true })
mkdirSync(target, { recursive: true })
cpSync(source, target, { recursive: true })

const ROUTES = [
  'events',
  'graph',
  'summary',
  'recall',
  'stats',
  'library',
  'config',
  'settings',
]

function walk(dir) {
  const entries = []
  for (const name of readdirSync(dir)) {
    const full = resolve(dir, name)
    const stat = statSync(full)
    if (stat.isDirectory()) {
      entries.push(...walk(full))
    } else {
      entries.push(full)
    }
  }
  return entries
}

function posixRelativePrefix(file) {
  const from = dirname(file)
  const rel = relative(from, target).split(sep).join('/')
  return rel ? `${rel}/` : './'
}

function rewritePluginPagePaths(file) {
  const ext = file.split('.').pop()
  if (!['html', 'txt', 'js'].includes(ext)) return

  const prefix = posixRelativePrefix(file)
  let text = readFileSync(file, 'utf8')

  if (ext === 'js') {
    text = text.replace(
      'let t="/_next/"',
      'let t=(()=>{let e=document.currentScript?.src;if(!e)return"/_next/";let t=new URL("../../",e).pathname;return t.endsWith("/")?t:`${t}/`})()',
    )
    writeFileSync(file, text, 'utf8')
    return
  }

  // AstrBot Plugin Pages rewrites relative resources and appends asset_token.
  // Root-relative Next export URLs would hit the AstrBot Dashboard root.
  text = text.replace(/(["'])\/_next\//g, `$1${prefix}_next/`)
  text = text.replace(/(["'])\/favicon\.ico/g, `$1${prefix}favicon.ico`)

  if (ext === 'html') {
    for (const route of ROUTES) {
      text = text.replace(
        new RegExp(`(href=\\\\?["'])/${route}(?:/)?(\\\\?["'])`, 'g'),
        `$1${prefix}${route}/$2`,
      )
    }
    text = text.replace(/(href=\\?["'])\/(\\?["'])/g, `$1${prefix}$2`)
  }

  writeFileSync(file, text, 'utf8')
}

for (const file of walk(target)) {
  rewritePluginPagePaths(file)
}

console.log(`Copied and patched static WebUI export to ${target}`)

import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(here, '..')
const projectRoot = resolve(frontendRoot, '..', '..')

// With basePath: '/api/pages/astrbot_plugin_moirai/moirai', 
// Next.js export puts files in out/api/pages/astrbot_plugin_moirai/moirai/
const basePath = '/api/pages/astrbot_plugin_moirai/moirai'
const source = resolve(frontendRoot, 'out', ...basePath.split('/').filter(Boolean))
const target = resolve(projectRoot, 'pages', 'moirai')

// Fallback: if basePath directory doesn't exist in 'out', use 'out' root
const effectiveSource = existsSync(source) ? source : resolve(frontendRoot, 'out')

if (!existsSync(effectiveSource)) {
  console.error(`Next export output not found: ${effectiveSource}`)
  process.exit(1)
}

console.log(`Copying from ${effectiveSource} to ${target}...`)
rmSync(target, { recursive: true, force: true })
mkdirSync(target, { recursive: true })
cpSync(effectiveSource, target, { recursive: true })

console.log(`Successfully copied static WebUI export to ${target}.`)
console.log(`No manual path patching required thanks to Next.js basePath.`)

import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
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

console.log(`Copied static WebUI export to ${target}`)

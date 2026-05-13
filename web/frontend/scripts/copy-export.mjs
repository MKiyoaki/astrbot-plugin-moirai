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
    // AstrBot Plugin Pages injects asset_token into <script src="..."> attributes that it
    // can statically rewrite (the initial HTML). But Turbopack loads additional chunks at
    // runtime via document.createElement('script') + src assignment — those URLs are
    // constructed programmatically and never pass through AstrBot's attribute rewriter,
    // so they arrive without asset_token and get a 401.
    //
    // Fix: when the Turbopack bootstrap script runs, extract asset_token from its own
    // src URL (which AstrBot has already injected the token into), then patch
    // document.createElement so every subsequently created <script> that targets a
    // _next/static/ path automatically carries that token.
    text = text.replace(
      'let t="/_next/"',
      `let t=(()=>{
        const _src=document.currentScript?.src||'';
        try{
          const _at=new URL(_src).searchParams.get('asset_token');
          if(_at){
            const _oce=document.createElement.bind(document);
            document.createElement=function(tag,...a){
              const el=_oce(tag,...a);
              if(typeof tag==='string'&&tag.toLowerCase()==='script'){
                const _desc=Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype,'src');
                let _v='';
                Object.defineProperty(el,'src',{configurable:true,
                  get(){return _v},
                  set(u){
                    if(typeof u==='string'&&u.includes('_next/static/')&&!u.includes('asset_token'))
                      u+=(u.includes('?')?'&':'?')+'asset_token='+_at;
                    _v=u;_desc?.set?.call(this,u);
                  }
                });
              }
              return el;
            };
          }
        }catch{}
        if(!_src)return"/_next/";
        const _t=new URL("../../",_src).pathname;
        return _t.endsWith("/")?_t:_t+"/";
      })()`,
    )
    writeFileSync(file, text, 'utf8')
    return
  }

  // AstrBot Plugin Pages rewrites relative resources and appends asset_token.
  // Root-relative Next export URLs would hit the AstrBot Dashboard root.
  text = text.replace(/(\\")\/_next\//g, `$1${prefix}_next/`)
  text = text.replace(/(\\")\/favicon\.ico/g, `$1${prefix}favicon.ico`)
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

/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development'

const nextConfig = {
  // Production: static export to out/. frontend_build.py then copies out/ →
  // pages/moirai/ with HTML-only path rewriting (absolute /_next/ → relative),
  // so AstrBot Plugin Pages can inject asset_token on the relative hrefs.
  // Dev: skip output so next dev + HMR + API rewrites work normally.
  ...(isDev ? {} : {
    output: 'export',
    distDir: 'out',
    basePath: '/api/pages/astrbot_plugin_moirai/moirai',
  }),

  images: {
    unoptimized: true,
  },

  trailingSlash: true,

  ...(isDev && { skipTrailingSlashRedirect: true }),

  async rewrites() {
    if (!isDev) return []
    const backendPort = process.env.BACKEND_PORT || '2654'
    return [
      {
        source: '/api/:path*',
        destination: `http://localhost:${backendPort}/api/:path*`,
      },
    ]
  },
}

export default nextConfig

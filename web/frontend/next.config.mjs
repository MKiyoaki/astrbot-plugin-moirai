/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development'

const nextConfig = {
  // Production: static export directly into pages/moirai/ (AstrBot Plugin Pages).
  // basePath tells Next.js the app is mounted at /plug/moirai, so all /_next/
  // asset URLs are emitted as /plug/moirai/_next/... — no post-build path rewriting needed.
  // Dev: no output/basePath so next dev + HMR + API rewrites work normally.
  ...(isDev ? {} : {
    output: 'export',
    distDir: 'out',
    basePath: '/plug/moirai',
    env: {
      NEXT_PUBLIC_BASE_PATH: '/plug/moirai',
    },
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

/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development'

const nextConfig = {
  // In production builds (next build), export static files to output/.
  // In dev mode (next dev), skip static-export so rewrites & HMR work normally.
  ...(isDev ? {} : { output: 'export', distDir: 'output' }),

  images: {
    unoptimized: true,
  },

  trailingSlash: true,

  // In dev mode, prevent Next.js from adding trailing-slash redirects so that
  // /api/* rewrites fire directly without an extra 308 round-trip.
  ...(isDev && { skipTrailingSlashRedirect: true }),

  async rewrites() {
    // Rewrites only apply in dev; in production the Python backend serves both
    // static files and /api/* routes from the same origin.
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

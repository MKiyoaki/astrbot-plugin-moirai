/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
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

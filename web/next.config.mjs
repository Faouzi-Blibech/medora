/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Dev server: also serve the app to phones and laptops on the local network (the laptop's LAN address changes
  // with the Wi-Fi). Production builds ignore this.
  allowedDevOrigins: ["192.168.*.*", "10.*.*.*", "172.*.*.*"],
};

export default nextConfig;

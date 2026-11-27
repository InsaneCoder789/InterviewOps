/** Static export: the story site needs no server and never talks to the API. */
export default {
  output: "export",
  reactStrictMode: true,
  images: { unoptimized: true },
  devIndicators: false,
  turbopack: { root: import.meta.dirname },
};

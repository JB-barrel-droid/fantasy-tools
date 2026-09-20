export default {
  async fetch() {
    return new Response("Trade Value Dashboard static assets are served by Sites.", {
      status: 404,
      headers: {"content-type": "text/plain; charset=utf-8"}
    });
  }
};

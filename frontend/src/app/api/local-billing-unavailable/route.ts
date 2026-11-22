function unavailable() {
  return new Response(null, { status: 404 });
}

export { unavailable as GET, unavailable as POST, unavailable as PUT,
  unavailable as PATCH, unavailable as DELETE };

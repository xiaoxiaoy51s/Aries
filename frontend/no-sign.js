// Dummy signer - skips code signing entirely
exports.default = async function(options) {
  console.log('[no-sign] Skipping code signing for:', options.path)
}

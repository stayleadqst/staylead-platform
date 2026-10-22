#!/usr/bin/env node
// Create lossless PNG companions for the nine guest-approved SVG illustrations.
// Requires the repository's installed sharp package; does not fetch dependencies.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const sharp = require('../../../../apps/web/node_modules/sharp');

async function main() {
const root = __dirname;
const manifestPath = path.join(root, 'media_manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));

for (const record of manifest.media_records) {
  if (record.media_type !== 'image/svg+xml') continue;
  const sourcePath = path.join(root, record.asset_path);
  const rasterRelative = record.asset_path.replace(/\.svg$/i, '.png');
  const rasterPath = path.join(root, rasterRelative);
  await sharp(sourcePath, { density: 144 }).png({ compressionLevel: 9, adaptiveFiltering: true }).toFile(rasterPath);
  const bytes = await fs.readFile(rasterPath);
  record.raster_asset_path = rasterRelative.split(path.sep).join('/');
  record.raster_media_type = 'image/png';
  record.raster_sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
  record.raster_size_bytes = bytes.length;
}

await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
console.log('Rasterized SVG fixtures and refreshed manifest PNG hashes/sizes.');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

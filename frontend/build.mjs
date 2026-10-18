import { build } from 'esbuild';
import { mkdir, rm, writeFile } from 'node:fs/promises';

await rm('static/dist', { recursive: true, force: true });
await mkdir('static/dist', { recursive: true });
const result = await build({
  entryPoints: { experience: 'frontend/experience.ts' },
  outdir: 'static/dist',
  bundle: true,
  minify: true,
  splitting: true,
  format: 'esm',
  target: ['es2022'],
  metafile: true,
  define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'linked',
});
await writeFile('frontend/build-meta.json', JSON.stringify(result.metafile, null, 2));
for (const [file, info] of Object.entries(result.metafile.outputs)) {
  console.log(`${file}: ${(info.bytes / 1024).toFixed(1)} kB`);
}

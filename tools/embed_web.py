"""Vloží malý samostatný web do flash; bez CDN a souborového systému."""
from pathlib import Path
import gzip
root=Path(__file__).resolve().parents[1]
data=gzip.compress((root/'firmware/web/index.html').read_bytes(),mtime=0)
rows=['  '+','.join(str(n) for n in data[i:i+24])+',' for i in range(0,len(data),24)]
(root/'firmware/BuzzerDisplay/web_assets.h').write_text('// Generováno tools/embed_web.py.\n#pragma once\n#include <cstdint>\nstatic const uint8_t web_gz[] = {\n'+'\n'.join(rows)+'\n};\n')
print(f'Web ve flash: {len(data)} bajtů')

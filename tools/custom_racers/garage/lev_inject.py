#!/usr/bin/env python3
"""
lev_inject.py - inyecta modelos .ctr (+ InstDefs) dentro de un .lev de CTR (PS1).

Formato contenedor (verificado con data.lev, selectkartcoco.ctr, crashselect.ctr):
    u32  dataSize
    u8   data[dataSize]          (punteros = offsets relativos al inicio de data)
    u32  mapBytes                (= 4 * N)
    u32  ptrMap[N]               (offsets, relativos a data, de cada u32 que es puntero)

Model (inicio de data en un .ctr):
    +0x00 char name[16]  +0x10 i16 id  +0x12 i16 numHeaders  +0x14 ptr headers

Cabecera Level (verificada contra garage_retail.lev: 17 instancias @0x1b0, 16 modelos, array @0x5f0):
    +0x0C numInstances  +0x10 ptrInstDefs  +0x14 numModels  +0x18 ptrModelsPtrs (Model*[])
    (+0x08 es otra estructura, no se toca)

InstDef: 0x40 bytes, name[16] en +0x00 y Model* en +0x10 (unico puntero; el resto NO se inventa:
viene de un .lev retail (--instdefs-from) o de un JSON con offsets explicitos).

Uso:
  python lev_inject.py dump   archivo.lev
  python lev_inject.py inject --lev data.lev --models-from-lev garage_retail.lev -o data_new.lev   (RECOMENDADO)
  python lev_inject.py inject --lev data.lev --ctr *.ctr --instdefs-from retail_garage.lev -o data_new.lev
  python lev_inject.py inject --lev data.lev --ctr *.ctr --instdefs instances.json      -o data_new.lev
  python lev_inject.py verify data_new.lev
"""
import argparse, json, struct, sys

LEV_NUM_INST, LEV_PTR_INST, LEV_NUM_MODELS, LEV_PTR_MODELS = 0x0C, 0x10, 0x14, 0x18
INSTDEF_SIZE, INSTDEF_PTRMODEL = 0x40, 0x10
ALIGN = 4


def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def put32(b, o, v): struct.pack_into('<I', b, o, v & 0xFFFFFFFF)
def cstr(b): return bytes(b).split(b'\0')[0].decode('ascii', 'replace')
def align(n, a=ALIGN): return (n + a - 1) // a * a


class Blob:
    def __init__(self, path):
        raw = open(path, 'rb').read()
        size = u32(raw, 0)
        self.data = bytearray(raw[4:4 + size])
        mb = u32(raw, 4 + size)
        if mb % 4 or 4 + size + 4 + mb != len(raw):
            raise SystemExit(f'{path}: tamaño inconsistente (data={size:#x}, map={mb:#x}, file={len(raw):#x})')
        self.ptrs = list(struct.unpack_from(f'<{mb // 4}I', raw, 8 + size))
        self.path = path

    def save(self, path):
        out = struct.pack('<I', len(self.data)) + bytes(self.data)
        out += struct.pack('<I', 4 * len(self.ptrs)) + struct.pack(f'<{len(self.ptrs)}I', *self.ptrs)
        open(path, 'wb').write(out)

    def check(self):
        n = len(self.data)
        errs = []
        for p in self.ptrs:
            if p % 4 or p + 4 > n:
                errs.append(f'entrada de mapa fuera de rango: {p:#x}')
                continue
            v = u32(self.data, p)
            if v > n:
                errs.append(f'puntero en {p:#x} -> {v:#x} fuera de data ({n:#x})')
        return errs


def model_at(blob, off):
    d = blob.data
    return dict(name=cstr(d[off:off + 16]), id=struct.unpack_from('<h', d, off + 0x10)[0],
                nhdr=struct.unpack_from('<h', d, off + 0x12)[0])


def read_level(lev):
    d = lev.data
    ni, pi, nm, pm = (u32(d, o) for o in (LEV_NUM_INST, LEV_PTR_INST, LEV_NUM_MODELS, LEV_PTR_MODELS))
    models = [u32(d, pm + 4 * i) for i in range(nm)] if nm else []
    insts = []
    for i in range(ni):
        o = pi + i * INSTDEF_SIZE
        raw = bytes(d[o:o + INSTDEF_SIZE])
        mp = u32(raw, INSTDEF_PTRMODEL)
        insts.append(dict(name=cstr(raw[:16]), model_ptr=mp,
                          model=model_at(lev, mp)['name'] if 0 < mp < len(d) - 0x18 else None, raw=raw))
    return ni, pi, nm, pm, models, insts


def cmd_dump(a):
    lev = Blob(a.file)
    print(f'{a.file}: data={len(lev.data):#x}  ptrs={len(lev.ptrs)}')
    mapset = set(lev.ptrs)
    print('-- cabecera (words no nulos < 0x200, o ptr del mapa):')
    for o in range(0, 0x200, 4):
        v = u32(lev.data, o)
        if v or o in mapset:
            print(f'  +{o:#05x} = {v:#010x} {"[ptr]" if o in mapset else ""}')
    ni, pi, nm, pm, models, insts = read_level(lev)
    print(f'-- numModels={nm} ptrModels={pm:#x} | numInstances={ni} ptrInstDefs={pi:#x}')
    for i, m in enumerate(models):
        print(f'  model[{i}] @{m:#x}', model_at(lev, m))
    for i, it in enumerate(insts):
        print(f'  inst[{i}] name={it["name"]!r} model={it["model"]!r}')
        print('     hex :', it['raw'].hex(' ', 4))
        print('     i16 :', list(struct.unpack('<32h', it['raw'])))
        print('     i32 :', list(struct.unpack('<16i', it['raw'])))


def cmd_verify(a):
    lev = Blob(a.file)
    errs = lev.check()
    ni, pi, nm, pm, models, insts = read_level(lev)
    print(f'models={nm} instances={ni} ptrs={len(lev.ptrs)} dup_ptrs={len(lev.ptrs) - len(set(lev.ptrs))}')
    for m in models:
        print('  model', model_at(lev, m))
    for it in insts:
        if it['model'] is None and ni:
            errs.append(f'InstDef {it["name"]!r} con Model* inválido {it["model_ptr"]:#x}')
        print('  inst ', it['name'], '->', it['model'])
    if ni and pi % 4 == 0 and pi + ni * INSTDEF_SIZE > len(lev.data):
        errs.append('array de InstDefs se sale de data')
    for p in (pi + i * INSTDEF_SIZE + INSTDEF_PTRMODEL for i in range(ni)):
        if p not in set(lev.ptrs):
            errs.append(f'ptrModel de InstDef en {p:#x} no está en el mapa')
    print('OK' if not errs else 'ERRORES:\n  ' + '\n  '.join(errs))
    sys.exit(1 if errs else 0)


def build_instdefs_template(a, models_by_name, model_addr):
    ret = Blob(a.instdefs_from)
    _, _, _, _, _, rinsts = read_level(ret)
    out, skipped = [], []
    tr = None
    if a.translate:
        if a.pos_offset is None:
            raise SystemExit('--translate requiere --pos-offset (offset del campo posición dentro del InstDef)')
        tr = [int(x) for x in a.translate.split(',')]
    fmt = '<3h' if a.pos_size == 2 else '<3i'
    for it in rinsts:
        key = (it['model'] or '').lower()
        if key not in models_by_name:
            skipped.append((it['name'], it['model']))
            continue
        raw = bytearray(it['raw'])
        put32(raw, INSTDEF_PTRMODEL, model_addr[key])
        if tr:
            p = list(struct.unpack_from(fmt, raw, a.pos_offset))
            struct.pack_into(fmt, raw, a.pos_offset, *[p[i] + tr[i] for i in range(3)])
        out.append(bytes(raw))
    return out, skipped


def build_instdefs_json(a, model_addr):
    spec = json.load(open(a.instdefs))
    lay = spec.get('layout', {})
    out = []
    for it in spec['instances']:
        key = it['model'].lower()
        if key not in model_addr:
            raise SystemExit(f'instancia referencia modelo inexistente: {it["model"]}')
        raw = bytearray(bytes.fromhex(it['raw_hex'])) if 'raw_hex' in it else bytearray(INSTDEF_SIZE)
        if len(raw) != INSTDEF_SIZE:
            raise SystemExit('raw_hex debe ser de 0x40 bytes')
        raw[:16] = it.get('name', it['model']).encode('ascii')[:15].ljust(16, b'\0')
        put32(raw, INSTDEF_PTRMODEL, model_addr[key])
        for field in ('scale', 'pos', 'rot'):
            if field in it:
                if f'{field}_off' not in lay or f'{field}_fmt' not in lay:
                    raise SystemExit(f'"{field}" usado pero falta layout.{field}_off / {field}_fmt '
                                     f'(no se asumen offsets: copiarlos de ModSDK/retail)')
                struct.pack_into('<' + lay[f'{field}_fmt'], raw, lay[f'{field}_off'], *it[field])
        out.append(bytes(raw))
    return out


class Slice:
    def __init__(self, data, ptrs):
        self.data, self.ptrs = bytearray(data), list(ptrs)


def retail_models(path, last_end=None):
    ret = Blob(path)
    d = ret.data
    ni, pi, nm, pm, mptrs, _ = read_level(ret)
    if not nm:
        raise SystemExit(f'{path}: no tiene modelos')
    starts = sorted(set(mptrs))
    ps = sorted(set(ret.ptrs))
    if last_end is None:
        ls = starts[-1]
        # fin del ultimo modelo: primera entrada del mapa cuyo destino cae >=0x8000 por delante (estructura ajena)
        last_end = next((p for p in ps if p >= ls and u32(d, p) > p and u32(d, p) - p >= 0x8000), len(d))
        print(f'  fin autodetectado del ultimo modelo: {last_end:#x} (revisar; override con --last-end)')
    ends = {s: e for s, e in zip(starts, starts[1:] + [last_end])}
    out = []
    for m in mptrs:                      # orden original del array Model*[]
        s, e = m, ends[m]
        sub = [p - s for p in ps if s <= p < e]
        bad = [p for p in sub if u32(d, s + p) and not (s <= u32(d, s + p) <= e)]
        if bad:
            raise SystemExit(f'modelo @{s:#x}: {len(bad)} puntero(s) salen del rango [{s:#x},{e:#x})')
        sl = Slice(d[s:e], sub)
        for p in sub:
            if u32(sl.data, p):
                put32(sl.data, p, u32(sl.data, p) - s)
        out.append((f'{path}#{model_at(ret, m)["name"]}', sl))
    return out


def cmd_inject(a):
    lev = Blob(a.lev)
    d = lev.data
    if u32(d, LEV_NUM_INST) or u32(d, LEV_NUM_MODELS):
        raise SystemExit('el .lev ya tiene modelos/instancias; este script solo inyecta sobre un lev vacío')
    errs = lev.check()
    if errs:
        raise SystemExit('lev de entrada inválido:\n  ' + '\n  '.join(errs[:10]))

    new_ptrs, model_addr, models_by_name, model_list = [], {}, {}, []
    srcs = []
    if a.models_from_lev:
        srcs += retail_models(a.models_from_lev, a.last_end)
        if not a.instdefs and not a.instdefs_from:
            a.instdefs_from = a.models_from_lev
    srcs += [(p, Blob(p)) for p in a.ctr]
    if not srcs:
        raise SystemExit('nada que inyectar: usar --ctr y/o --models-from-lev')
    for path, c in srcs:
        ext = [p for p in c.ptrs if p % 4 or p + 4 > len(c.data) or u32(c.data, p) > len(c.data)]
        if ext and a.external == 'fail':
            lines = [f'  data+{p:#x} -> {u32(c.data, p):#x}' for p in ext]
            raise SystemExit(f'{path}: {len(ext)} puntero(s) del mapa apuntan FUERA del .ctr (data={len(c.data):#x}):\n'
                             + '\n'.join(lines) + '\nEl .ctr probablemente depende de datos externos (p.ej. animaciones). '
                             'Usar --external zero solo para pruebas.')
        for p in ext:          # --external zero: se anula y se saca del mapa
            put32(c.data, p, 0)
        c.ptrs = [p for p in c.ptrs if p not in set(ext)]
        if ext:
            print(f'! {path}: {len(ext)} puntero(s) externo(s) anulados (modelo SIN esos datos)')
        info = model_at(c, 0)
        key = info['name'].lower()
        if key in models_by_name:
            raise SystemExit(f'modelo duplicado: {info["name"]}')
        base = align(len(d))
        d.extend(b'\0' * (base - len(d)))
        d.extend(c.data)
        nulls = 0
        for p in c.ptrs:
            v = u32(c.data, p)
            if v == 0:          # null: se deja en 0 y fuera del mapa (así sigue null en runtime)
                nulls += 1
                continue
            put32(d, base + p, v + base)
            new_ptrs.append(base + p)
        models_by_name[key] = info
        model_addr[key] = base
        model_list.append(key)
        print(f'+ {path}: base={base:#x} size={len(c.data):#x} ptrs={len(c.ptrs) - nulls} (nulos omitidos={nulls}) '
              f'name={info["name"]!r} id={info["id"]} ({info["id"] & 0xFFFF:#x}) nhdr={info["nhdr"]}')

    # array Model*[]
    arr = align(len(d))
    d.extend(b'\0' * (arr - len(d)))
    for i, k in enumerate(model_list):
        d.extend(struct.pack('<I', model_addr[k]))
        new_ptrs.append(arr + 4 * i)

    # InstDefs
    if a.instdefs_from:
        insts, skipped = build_instdefs_template(a, models_by_name, model_addr)
        for s in skipped:
            print(f'! InstDef retail sin modelo inyectado, omitida: name={s[0]!r} model={s[1]!r}')
    elif a.instdefs:
        insts = build_instdefs_json(a, model_addr)
    else:
        insts = []
    ib = align(len(d))
    d.extend(b'\0' * (ib - len(d)))
    for i, raw in enumerate(insts):
        d.extend(raw)
        new_ptrs.append(ib + i * INSTDEF_SIZE + INSTDEF_PTRMODEL)

    # cabecera
    put32(d, LEV_NUM_MODELS, len(model_list)); put32(d, LEV_PTR_MODELS, arr)
    put32(d, LEV_NUM_INST, len(insts));        put32(d, LEV_PTR_INST, ib)
    have = set(lev.ptrs)
    for h in (LEV_PTR_INST, LEV_PTR_MODELS):
        if h not in have:
            new_ptrs.append(h)
    lev.ptrs += sorted(set(p for p in new_ptrs if p not in have))
    errs = lev.check()
    if errs:
        raise SystemExit('resultado inválido:\n  ' + '\n  '.join(errs[:10]))
    lev.save(a.out)
    print(f'-> {a.out}: data={len(d):#x} models={len(model_list)} instances={len(insts)} ptrs={len(lev.ptrs)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('dump'); s.add_argument('file'); s.set_defaults(f=cmd_dump)
    s = sp.add_parser('verify'); s.add_argument('file'); s.set_defaults(f=cmd_verify)
    s = sp.add_parser('inject')
    s.add_argument('--lev', required=True); s.add_argument('--ctr', nargs='+', default=[])
    s.add_argument('--models-from-lev', help='.lev retail del que copiar TODOS los modelos (y sus 17 InstDef)')
    s.add_argument('--last-end', type=lambda x: int(x, 0), help='fin (offset en el .lev retail) del ultimo modelo; por defecto se autodetecta')
    s.add_argument('-o', '--out', required=True)
    g = s.add_mutually_exclusive_group()
    g.add_argument('--instdefs-from', help='.lev retail del que copiar los InstDef (solo cambia Model*)')
    g.add_argument('--instdefs', help='JSON con instancias + layout explícito')
    s.add_argument('--translate', help='dx,dy,dz sumado a la posición de cada InstDef copiado')
    s.add_argument('--pos-offset', type=lambda x: int(x, 0), help='offset de la posición dentro del InstDef')
    s.add_argument('--pos-size', type=int, choices=(2, 4), default=2, help='bytes por componente (2=i16, 4=i32)')
    s.add_argument('--external', choices=('fail', 'zero'), default='fail',
                   help='qué hacer con punteros del mapa que apuntan fuera del .ctr')
    s.set_defaults(f=cmd_inject)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
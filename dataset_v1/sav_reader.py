"""Lector mínimo de archivos SPSS .sav (sin dependencias externas)."""
import struct, math
import numpy as np
import pandas as pd
from array import array

def read_sav(path):
    buf = open(path, "rb").read()
    pos = 0
    assert buf[:4] == b"$FL2", "No es un .sav"
    layout, case_size, compression, weight_idx, ncases = struct.unpack("<5i", buf[64:84])
    enc = "latin-1"
    pos = 176
    vars_ = []            # una entrada por registro de variable (incluye continuaciones)
    value_labels = []     # (lista de índices de var, {valor: etiqueta})
    long_names = {}
    very_long = {}
    pending = None
    while True:
        rec = struct.unpack("<i", buf[pos:pos+4])[0]; pos += 4
        if rec == 2:
            typ, has_label, n_miss, pr, wr = struct.unpack("<5i", buf[pos:pos+20]); pos += 20
            name = buf[pos:pos+8].decode(enc).strip(); pos += 8
            label = ""
            if has_label:
                ln = struct.unpack("<i", buf[pos:pos+4])[0]; pos += 4
                label = buf[pos:pos+ln].decode(enc, "replace"); pos += (ln + 3) // 4 * 4
            miss = []
            if n_miss:
                k = abs(n_miss)
                miss = list(struct.unpack(f"<{k}d", buf[pos:pos+8*k])); pos += 8*k
            vars_.append(dict(typ=typ, name=name, label=label, miss=miss, n_miss=n_miss, fmt=pr))
        elif rec == 3:
            cnt = struct.unpack("<i", buf[pos:pos+4])[0]; pos += 4
            pairs = []
            for _ in range(cnt):
                val = buf[pos:pos+8]; pos += 8
                ln = buf[pos]; pos += 1
                lab = buf[pos:pos+ln].decode(enc, "replace"); pos += ln
                pos += (-(1 + ln)) % 8
                pairs.append((val, lab))
            pending = pairs
        elif rec == 4:
            cnt = struct.unpack("<i", buf[pos:pos+4])[0]; pos += 4
            idx = list(struct.unpack(f"<{cnt}i", buf[pos:pos+4*cnt])); pos += 4*cnt
            value_labels.append((idx, pending)); pending = None
        elif rec == 6:
            n = struct.unpack("<i", buf[pos:pos+4])[0]; pos += 4 + 80*n
        elif rec == 7:
            sub, size, count = struct.unpack("<3i", buf[pos:pos+12]); pos += 12
            data = buf[pos:pos+size*count]; pos += size*count
            if sub == 13:
                for item in data.decode(enc, "replace").split("\t"):
                    if "=" in item:
                        s, l = item.split("=", 1); long_names[s.strip()] = l.strip()
            elif sub == 14:
                for item in data.decode(enc, "replace").split("\t"):
                    if "=" in item:
                        s, l = item.split("=", 1); very_long[s.strip()] = int(l.strip("\x00 "))
            elif sub == 20:
                e = data.decode("ascii", "ignore").strip()
                enc = {"UTF-8": "utf-8", "65001": "utf-8"}.get(e, enc)
        elif rec == 999:
            pos += 4
            break
        else:
            raise ValueError(f"Registro desconocido {rec} en {pos}")
    # --- datos ---
    assert compression == 1, "solo compresión por bytecode"
    n_slots = len(vars_)
    total = ncases * n_slots
    out = array("Q")
    SPACES = struct.unpack("<Q", b"        ")[0]
    SYSMIS = struct.unpack("<Q", struct.pack("<d", -1.7976931348623157e308))[0]
    raw = np.frombuffer(buf, dtype=np.uint8, offset=pos)
    p = pos
    n = len(buf)
    unpack_d = struct.Struct("<d").pack
    unpack_Q = struct.Struct("<Q").unpack
    while len(out) < total and p < n:
        ctrl = buf[p:p+8]; p += 8
        for c in ctrl:
            if c == 0:
                continue
            elif c == 252:
                p = n; break
            elif c == 253:
                out.append(unpack_Q(buf[p:p+8])[0]); p += 8
            elif c == 254:
                out.append(SPACES)
            elif c == 255:
                out.append(SYSMIS)
            else:
                out.append(unpack_Q(unpack_d(float(c - 100)))[0])
            if len(out) >= total: break
    arr = np.frombuffer(out, dtype=np.uint64)[:total].reshape(ncases, n_slots)
    return dict(arr=arr, vars=vars_, value_labels=value_labels, long_names=long_names,
                very_long=very_long, ncases=ncases, enc=enc)

def to_frames(d):
    arr, vars_ = d["arr"], d["vars"]
    cols, meta = {}, []
    i = 0
    while i < len(vars_):
        v = vars_[i]
        if v["typ"] == -1:
            i += 1; continue
        # contar continuaciones
        j = i + 1
        while j < len(vars_) and vars_[j]["typ"] == -1: j += 1
        name = d["long_names"].get(v["name"], v["name"])
        if v["typ"] == 0:
            vals = arr[:, i].view(np.float64).copy()
            vals[vals < -1e300] = np.nan
            cols[name] = vals
            meta.append(dict(var=name, tipo="num", etiqueta=v["label"], slot=i))
        else:
            w = v["typ"]
            chunk = np.ascontiguousarray(arr[:, i:j])
            b = chunk.view("S8").reshape(len(chunk), -1)
            s = np.array([b"".join(r)[:w].rstrip() for r in b]).astype(str) if False else \
                [b"".join(r)[:w].decode(d["enc"], "replace").rstrip() for r in b]
            cols[name] = s
            meta.append(dict(var=name, tipo=f"str{w}", etiqueta=v["label"], slot=i))
        i = j
    df = pd.DataFrame(cols)
    # etiquetas de valor
    meta = pd.DataFrame(meta)
    slot2name = {m["slot"]: m["var"] for _, m in meta.iterrows()}
    vlabs = {}
    for idx, pairs in d["value_labels"]:
        for k in idx:
            nm = slot2name.get(k - 1)
            if nm is None: continue
            dct = {}
            es_str = str(meta[meta['var'] == nm].iloc[0]['tipo']).startswith('str')
            for val, lab in pairs:
                if es_str:
                    key = val.decode(d["enc"], "replace").rstrip()
                else:
                    num = struct.unpack("<d", val)[0]
                    key = int(num) if float(num).is_integer() else num
                dct[key] = lab
            vlabs[nm] = dct
    return df, meta, vlabs

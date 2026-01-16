# Troubleshooting para diffs fuera de git

Objetivo: generar diffs sin depender de que el archivo esté trackeado y sin que el pager bloquee la terminal.

## 1. Crear snapshot “BEFORE”

```bash
python tools/snapshot_file.py \
  --src ../tools/sifen_signature_crypto_verify.py \
  --dst /tmp/sifen_signature_crypto_verify.BEFORE.py
```

## 2. Editar el archivo con libertad

```bash
vim ../tools/sifen_signature_crypto_verify.py
```

## 3. Generar diff sin pager

```bash
python tools/make_diff_no_pager.py \
  --a /tmp/sifen_signature_crypto_verify.BEFORE.py \
  --b ../tools/sifen_signature_crypto_verify.py \
  --out /tmp/sifen_signature_crypto_verify.diff \
  --stat
```

El script siempre:
- usa `git --no-pager diff --no-index` si está disponible,
- cae a `difflib.unified_diff` si no hay git,
- respeta un límite de 5 MB (configurable con `--max-bytes`),
- muestra ruta del diff, líneas y bytes.

## Mini test manual (correr desde `tesaka-cv/`)

```bash
# 1) Snapshot “antes”
python tools/snapshot_file.py \
  --src ../tools/sifen_signature_crypto_verify.py \
  --dst /tmp/sifen_signature_crypto_verify.BEFORE.py

# 2) (Editar el archivo a gusto...)
#    p.ej. echo "# test" >> ../tools/sifen_signature_crypto_verify.py

# 3) Generar diff sin pager y guardar en /tmp
python tools/make_diff_no_pager.py \
  --a /tmp/sifen_signature_crypto_verify.BEFORE.py \
  --b ../tools/sifen_signature_crypto_verify.py \
  --out /tmp/sifen_signature_crypto_verify.diff \
  --stat

# 4) Medir tamaño (sin abrir pager)
wc -l /tmp/sifen_signature_crypto_verify.diff
```

La salida del script confirma que **no** se abrió pager y que el diff quedó grabado en `/tmp/sifen_signature_crypto_verify.diff`.

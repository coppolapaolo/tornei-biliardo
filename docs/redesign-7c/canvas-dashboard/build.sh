#!/bin/sh
# Assembla gli artboard .dc.html da sorgenti/: testa + CSS 7c condiviso +
# (eventuale CSS specifico) + sprite delle icone + corpo.
cd "$(dirname "$0")" || exit 1
for name in "$@"; do
  out="$name.dc.html"
  {
    cat sorgenti/head.part
    cat sorgenti/base.css
    case "$name" in *Desktop) cat sorgenti/desktop.css;; esac
    case "$name" in Giocatore[ABC]|Direttore[ABC]|Ospite[ABC]|Caso*|Tessera*|Concluse|Storico) cat sorgenti/extra.css;; esac
    case "$name" in Tessera*|Concluse|Storico) cat sorgenti/tessera.css;; esac
    if [ -f "sorgenti/$name.css" ]; then cat "sorgenti/$name.css"; fi
    printf '  </style>\n</helmet>\n'
    cat sorgenti/icons.part
    cat "sorgenti/$name.body"
    printf '</x-dc>\n</body>\n</html>\n'
  } > "$out"
  echo "$out"
done

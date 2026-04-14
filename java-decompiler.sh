function decompile-jar() {
  trap "return" SIGINT
  JARFILE="$1"
  OUTDIR="_$(basename $JARFILE .jar)"

  [[ ! -n "${JARFILE}" ]] && echo "Usage: ${0} file.jar" && return

  if command -v procyon-decompiler >/dev/null; then 
    procyon-decompiler -jar "$JARFILE" -o "$OUTDIR"
    return
  fi
  if command -v cfr >/dev/null; then 
    cfr "$JARFILE" --outputpath "$OUTDIR"
    return
  fi
  if command -v jad >/dev/null; then
    unzip "$JARFILE" -d "$OUTDIR"
    pushd "$OUTDIR"

    mkdir ./_decomp/
    find . -type f -name '*.class' | \
    while read JAVAFILE; do
      DESTINATION="./_decomp/$(dirname $JAVAFILE)"
      mkdir -p "$DESTINATION"
      jad -s ".java" -d "$DESTINATION" "$JAVAFILE"
    done

    popd
    return
  fi

  echo "Install procyon | cfr | jad"
  trap - SIGINT
}

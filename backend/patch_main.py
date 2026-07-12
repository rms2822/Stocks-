"""
patch_main.py — points main.py's 3 fundamental call sites at the shared input
builder (build_fundamental_kwargs), so the new quality factors flow through every
endpoint and /portfolio stops dropping dividend/roe.

Run once from the backend dir:   python patch_main.py
It backs up main.py first and only touches the 3 call expressions.
"""
import re, sys, os, datetime, py_compile

PATH = os.path.join("app", "main.py")
CALL = "compute_fundamental_analysis("
IMPORT_ANCHOR = "from .analysis.fundamental import compute_fundamental_analysis"
IMPORT_LINE = "from .analysis.fundamental_inputs import build_fundamental_kwargs"


def find_call_span(text, start):
    """Return (begin, end) covering compute_fundamental_analysis(...) with balanced parens."""
    open_paren = text.index("(", start)
    depth, i = 0, open_paren
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise ValueError("unbalanced parens")


def patch(text):
    out, idx, n = [], 0, 0
    while True:
        j = text.find(CALL, idx)
        if j == -1:
            out.append(text[idx:])
            break
        begin, end = find_call_span(text, j)
        block = text[begin:end]
        rowvar = "fund_row" if "fund_row" in block else "fund"
        out.append(text[idx:begin])
        out.append(f"compute_fundamental_analysis(**build_fundamental_kwargs(stock, {rowvar}))")
        idx = end
        n += 1
    return "".join(out), n


def main():
    if not os.path.exists(PATH):
        sys.exit(f"Can't find {PATH} — run this from the backend dir.")
    text = open(PATH, encoding="utf-8").read()

    new, n = patch(text)
    if n != 3:
        print(f"WARNING: expected 3 call sites, patched {n}. Aborting — review manually.")
        sys.exit(1)

    if IMPORT_LINE not in new:
        new = new.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + "\n" + IMPORT_LINE, 1)

    bak = PATH + ".bak." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    open(bak, "w", encoding="utf-8").write(text)
    open(PATH, "w", encoding="utf-8").write(new)

    try:
        py_compile.compile(PATH, doraise=True)
    except py_compile.PyCompileError as e:
        open(PATH, "w", encoding="utf-8").write(text)   # roll back
        sys.exit(f"Patched file failed to compile — rolled back.\n{e}")

    print(f"Patched {n} call sites + added import. Backup: {bak}")
    print("main.py compiles clean.")


if __name__ == "__main__":
    main()

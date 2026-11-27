import React from "react";

function renderInline(text: string): React.ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|\[C\d+\])/g);
  return tokens.map((token, idx) => {
    if (token.startsWith("**") && token.endsWith("**") && token.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-white">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (/^\[C\d+\]$/.test(token)) {
      return (
        <span
          key={idx}
          className="mx-0.5 inline-flex items-center rounded border border-indigo-700/60 bg-indigo-950/90 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-300"
        >
          {token}
        </span>
      );
    }
    return <React.Fragment key={idx}>{token}</React.Fragment>;
  });
}

function isTableRow(line: string): boolean {
  return line.startsWith("|") && line.endsWith("|");
}

function isSeparatorRow(line: string): boolean {
  return /^\|[\s:|-]+\|$/.test(line);
}

function parseCells(line: string): string[] {
  return line
    .slice(1, -1)
    .split("|")
    .map((c) => c.trim());
}

export function MarkdownAnswer({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];
  let tableRows: string[] = [];

  const flushList = (keyPrefix: number) => {
    if (listItems.length === 0) return;
    blocks.push(
      <ul
        key={`list-${keyPrefix}`}
        className="list-disc space-y-1.5 pl-5 text-sm text-gray-200"
      >
        {listItems.map((item, i) => (
          <li key={i} className="leading-relaxed">
            {renderInline(item)}
          </li>
        ))}
      </ul>
    );
    listItems = [];
  };

  const flushTable = (keyPrefix: number) => {
    if (tableRows.length === 0) return;
    const filtered = tableRows.filter((row) => !isSeparatorRow(row));
    if (filtered.length > 0) {
      const headers = parseCells(filtered[0]);
      const bodyRows = filtered.slice(1).map(parseCells);
      blocks.push(
        <div
          key={`table-${keyPrefix}`}
          className="overflow-x-auto rounded-lg border border-gray-800"
        >
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-950 text-gray-300">
              <tr>
                {headers.map((h, i) => (
                  <th key={i} className="border-b border-gray-800 px-3 py-2 font-semibold">
                    {renderInline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800 text-gray-200">
              {bodyRows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-2 align-top">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    tableRows = [];
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) {
      flushList(index);
      flushTable(index);
      return;
    }

    if (isTableRow(line)) {
      flushList(index);
      tableRows.push(line);
      return;
    }
    flushTable(index);

    if (line.startsWith("### ") || line.startsWith("## ") || line.startsWith("# ")) {
      flushList(index);
      const headingText = line.replace(/^#{1,3}\s+/, "");
      blocks.push(
        <h4 key={`h-${index}`} className="pt-2 text-sm font-bold text-indigo-300">
          {renderInline(headingText)}
        </h4>
      );
      return;
    }

    if (line.startsWith("- ") || line.startsWith("* ")) {
      listItems.push(line.slice(2));
      return;
    }

    flushList(index);
    blocks.push(
      <p key={`p-${index}`} className="text-sm leading-relaxed text-gray-100">
        {renderInline(line)}
      </p>
    );
  });

  flushList(lines.length);
  flushTable(lines.length);

  return <div className="space-y-2.5">{blocks}</div>;
}

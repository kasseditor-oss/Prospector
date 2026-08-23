"use client";

/**
 * A sortable column header.
 *
 * Both tables need one and neither should own it: the channels table and the
 * posts table sort different columns, but a header that announces itself
 * differently between the two would be a bug the user feels and cannot name.
 *
 * The control is a real button rather than a click handler on the cell, so
 * sorting is reachable by keyboard and announced as an action.
 */

type Props<K extends string> = {
  label: string;
  k: K;
  sortKey: K;
  sortDir: -1 | 1;
  onSort: (k: K) => void;
};

export function SortableTh<K extends string>({
  label,
  k,
  sortKey,
  sortDir,
  onSort,
}: Props<K>) {
  const active = sortKey === k;
  const order = active ? (sortDir === -1 ? "decrescente" : "crescente") : "sem ordenação";

  return (
    <th
      scope="col"
      className="sortable"
      aria-sort={active ? (sortDir === -1 ? "descending" : "ascending") : undefined}
    >
      <button type="button" className="th-btn" onClick={() => onSort(k)}>
        {label}
        <span className="arrow" aria-hidden="true">
          {active && sortDir === 1 ? "▲" : "▼"}
        </span>
        <span className="sr">
          Ordenar por {label}. Atualmente {order}.
        </span>
      </button>
    </th>
  );
}

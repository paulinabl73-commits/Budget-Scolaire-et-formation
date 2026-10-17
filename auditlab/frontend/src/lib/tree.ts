export interface TreeNode<T> {
  item: T;
  children: TreeNode<T>[];
}

/** Construit l'arborescence à partir d'une liste à plat (id, parent_id), triée par nom. */
export function buildTree<T extends { id: string; parent_id: string | null; nom: string }>(
  items: T[],
): TreeNode<T>[] {
  const nodes = new Map(items.map((i) => [i.id, { item: i, children: [] as TreeNode<T>[] }]));
  const roots: TreeNode<T>[] = [];
  for (const node of nodes.values()) {
    const parent = node.item.parent_id ? nodes.get(node.item.parent_id) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  const sort = (list: TreeNode<T>[]) => {
    list.sort((a, b) => a.item.nom.localeCompare(b.item.nom, "fr"));
    list.forEach((n) => sort(n.children));
  };
  sort(roots);
  return roots;
}

/** Identifiants de l'entité et de tous ses descendants (parents interdits lors d'un déplacement). */
export function descendantIds<T extends { id: string; parent_id: string | null }>(
  items: T[],
  id: string,
): Set<string> {
  const result = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const i of items) {
      if (i.parent_id && result.has(i.parent_id) && !result.has(i.id)) {
        result.add(i.id);
        grew = true;
      }
    }
  }
  return result;
}

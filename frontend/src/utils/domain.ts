// Domaine de filtre façon Odoo (arbre ET/OU) — MÊME format que `IrModelAccess.domain` côté backend
// (voir backend/app/core/access_control.py) : liste de tuples préfixés, connecteurs '&'/'|'/'!'.
// Portage volontairement partiel : contrairement au compilateur backend, celui-ci n'évalue que des
// champs DIRECTS d'un objet JS déjà aplati (pas de chemin pointé multi-relations `a.b.c`, pas de
// valeur magique `user.id`) — ce sont des concepts serveur/SQL sans équivalent simple sur les items
// déjà chargés en mémoire par fetchAllGenericItems. Fonctions pures, sans dépendance Vue — même
// esprit que services/urlState.ts.

export type DomainOperator = '=' | '!=' | '>' | '<' | '>=' | '<=' | 'in' | 'not in' | 'like' | 'ilike';
export type DomainConnector = '&' | '|' | '!';
export type DomainCondition = [string, DomainOperator, any];
export type DomainToken = DomainConnector | DomainCondition;
// Domaine sérialisé (persisté/échangé avec le backend) : liste à plat de tokens préfixés — les
// termes de haut niveau non consommés par un connecteur explicite sont implicitement combinés en ET
// (même convention que compile_domain côté backend).
export type DomainNode = DomainToken[];

export const DOMAIN_OPERATORS: DomainOperator[] = ['=', '!=', '>', '<', '>=', '<=', 'in', 'not in', 'like', 'ilike'];

// Opérateurs pertinents selon le type de champ (voir FormField.type, GenericList.vue) — pilote le
// sélecteur d'opérateur du constructeur de domaine (GenericListDomainGroupEditor.vue).
export function operatorsForFieldType(type: string): DomainOperator[] {
  switch (type) {
    case 'text':
      return ['=', '!=', 'like', 'ilike'];
    case 'number':
    case 'duration':
    case 'date':
      return ['=', '!=', '>', '<', '>=', '<='];
    case 'select':
      return ['=', '!=', 'in', 'not in'];
    case 'boolean':
    case 'color':
    default:
      return ['=', '!='];
  }
}

// Un champ est utilisable comme condition de filtre sauf s'il est many2many (multiselect), one2many
// "possédé" (resource + parentField tous deux présents), ou json/binary — même exclusion que
// isFieldGroupable (GenericList.vue), fonction séparée car les deux notions peuvent diverger.
export function isFieldFilterableInDomain(field: { type: string; resource?: string; parentField?: string }): boolean {
  if (field.type === 'multiselect') return false;
  if (field.resource && field.parentField) return false;
  if (field.type === 'json' || field.type === 'binary') return false;
  return true;
}

function evalCondition(item: any, field: string, op: DomainOperator, value: any): boolean {
  const actual = item ? item[field] : undefined;
  switch (op) {
    case '=':
      return actual === value;
    case '!=':
      return actual !== value;
    case '>':
      return actual != null && actual > value;
    case '<':
      return actual != null && actual < value;
    case '>=':
      return actual != null && actual >= value;
    case '<=':
      return actual != null && actual <= value;
    case 'in':
      return Array.isArray(value) && value.includes(actual);
    case 'not in':
      return Array.isArray(value) && !value.includes(actual);
    case 'like':
      // Toujours substring côté backend (col.like(f"%{v}%"), access_control.py) — jamais de
      // wildcards SQL à interpréter ici, portage direct en .includes().
      return String(actual ?? '').includes(String(value ?? ''));
    case 'ilike':
      return String(actual ?? '').toLowerCase().includes(String(value ?? '').toLowerCase());
    default:
      throw new Error(`Opérateur de domaine non supporté : ${op}`);
  }
}

// Portage direct de _compile_term (access_control.py), évalué contre l'objet JS au lieu d'être
// compilé en clause SQL. Lève une erreur sur un domaine structurellement invalide (jeton inconnu,
// tuple malformé) — à l'appelant de décider du repli (voir evaluateDomain ci-dessous, qui absorbe
// cette erreur pour ne jamais faire planter un filtrage en lot).
function evalTerm(item: any, domain: DomainToken[], pos: number): [boolean, number] {
  const token = domain[pos];
  if (token === undefined) {
    throw new Error('Domaine de filtre incomplet.');
  }
  if (token === '&') {
    const [left, pos1] = evalTerm(item, domain, pos + 1);
    const [right, pos2] = evalTerm(item, domain, pos1);
    return [left && right, pos2];
  }
  if (token === '|') {
    const [left, pos1] = evalTerm(item, domain, pos + 1);
    const [right, pos2] = evalTerm(item, domain, pos1);
    return [left || right, pos2];
  }
  if (token === '!') {
    const [operand, pos1] = evalTerm(item, domain, pos + 1);
    return [!operand, pos1];
  }
  const [field, op, value] = token as DomainCondition;
  return [evalCondition(item, field, op, value), pos + 1];
}

// Évalue un domaine (arbre ET/OU) contre UN item déjà aplati (props.items de GenericList.vue).
// Ne lève jamais : un domaine structurellement invalide (URL bricolée à la main, réponse serveur
// corrompue) fait considérer l'item comme NON filtré (visible) plutôt que de casser tout le tableau
// — un faux positif ponctuel est moins grave qu'une liste qui se vide silencieusement.
export function evaluateDomain(item: any, domain: DomainNode | null | undefined): boolean {
  if (!domain || domain.length === 0) return true;
  try {
    let pos = 0;
    let result = true;
    let first = true;
    while (pos < domain.length) {
      const [value, nextPos] = evalTerm(item, domain, pos);
      result = first ? value : result && value; // termes de haut niveau implicitement ET
      first = false;
      pos = nextPos;
    }
    return result;
  } catch (e) {
    console.warn('evaluateDomain: domaine invalide, ignoré pour cet item.', e);
    return true;
  }
}

// --- Conversions arbre <-> notation préfixée -------------------------------------------------
// L'arbre ci-dessous n'est qu'une représentation plus commode à éditer récursivement dans l'UI
// (GenericListDomainGroupEditor.vue) que la notation préfixée persistée/échangée avec le backend.
// Volontairement plus restreint que le domaine complet : seuls '&'/'|' sont représentables (pas de
// NOT) — cohérent avec la demande d'un arbre ET/OU, pas d'un éditeur de domaine Odoo complet.

export interface DomainConditionNode {
  field: string;
  operator: DomainOperator;
  value: any;
}

export interface DomainGroupNode {
  connector: '&' | '|';
  children: Array<DomainGroupNode | DomainConditionNode>;
}

export function isDomainGroupNode(node: DomainGroupNode | DomainConditionNode): node is DomainGroupNode {
  return (node as DomainGroupNode).connector !== undefined;
}

function nodeToPrefix(node: DomainGroupNode | DomainConditionNode): DomainToken[] {
  if (!isDomainGroupNode(node)) {
    return [[node.field, node.operator, node.value]];
  }
  const childTokenLists = node.children.map(nodeToPrefix);
  if (childTokenLists.length === 0) return [];
  if (childTokenLists.length === 1) return childTokenLists[0];
  // Notation Odoo : (n-1) connecteurs préfixés avant les n termes, dans l'ordre.
  const connectorTokens: DomainToken[] = new Array(childTokenLists.length - 1).fill(node.connector);
  return [...connectorTokens, ...childTokenLists.flat()];
}

export function domainTreeToPrefix(tree: DomainGroupNode): DomainNode {
  if (tree.children.length === 0) return [];
  return nodeToPrefix(tree);
}

function mergeIntoChildren(connector: '&' | '|', node: DomainGroupNode | DomainConditionNode): Array<DomainGroupNode | DomainConditionNode> {
  // Chaîne de même connecteur (ex: ["&","&",t1,t2,t3]) : aplatie en un seul groupe à 3 enfants
  // plutôt que reconstruite en sous-groupes imbriqués — plus lisible/éditable dans l'UI.
  if (isDomainGroupNode(node) && node.connector === connector) return node.children;
  return [node];
}

function parseTerm(domain: DomainToken[], pos: number): [DomainGroupNode | DomainConditionNode, number] {
  const token = domain[pos];
  if (token === undefined) {
    throw new Error('Domaine de filtre incomplet.');
  }
  if (token === '&' || token === '|') {
    const [left, pos1] = parseTerm(domain, pos + 1);
    const [right, pos2] = parseTerm(domain, pos1);
    return [{ connector: token, children: [...mergeIntoChildren(token, left), ...mergeIntoChildren(token, right)] }, pos2];
  }
  if (token === '!') {
    // NOT non représentable dans l'arbre ET/OU de l'éditeur visuel (v1) — voir docstring de
    // section. Le domaine reste néanmoins évaluable par evaluateDomain, seule sa RECONSTRUCTION en
    // arbre pour la popin échoue explicitement (l'appelant doit alors proposer de repartir d'un
    // filtre vide plutôt que d'éditer celui-ci).
    throw new Error('Opérateur "!" non supporté par le constructeur visuel de filtre.');
  }
  const [field, operator, value] = token as DomainCondition;
  return [{ field, operator, value }, pos + 1];
}

export function prefixToDomainTree(domain: DomainNode | null | undefined): DomainGroupNode {
  if (!domain || domain.length === 0) return { connector: '&', children: [] };
  let pos = 0;
  const terms: Array<DomainGroupNode | DomainConditionNode> = [];
  while (pos < domain.length) {
    const [node, nextPos] = parseTerm(domain, pos);
    terms.push(node);
    pos = nextPos;
  }
  if (terms.length === 1 && isDomainGroupNode(terms[0])) return terms[0] as DomainGroupNode;
  return { connector: '&', children: terms };
}

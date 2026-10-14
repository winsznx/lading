import type { Decision, HoldCode, Market, PlanResponse, Scenario, Slot } from "../api/types";

export interface CardModel {
  key: string;
  batchId: string;
  commodity: string;
  kg: number;
  totalKg: number;
  split: boolean;
  saleH: number | null;
  marginH: number | null;
  shelfH: number | null;
  discount: number;
  locked: boolean;
  dispatched: boolean;
  marketId: string;
  slotId: string;
}

export interface ColumnModel {
  slot: Slot;
  loadKg: number;
  capacityKg: number;
  trucksAvailable: number;
  trucksUsed: number;
  cardCount: number;
  collapsed: boolean;
  departed: boolean;
}

export interface RowModel {
  market: Market;
  cells: Map<string, CardModel[]>;
  cardCount: number;
  kg: number;
}

export interface TrayItem {
  batchId: string;
  commodity: string;
  kg: number;
  shelfH: number;
  holdCode: HoldCode | null;
  reason: string;
}

export interface BoardModel {
  columns: ColumnModel[];
  rows: RowModel[];
  held: TrayItem[];
  infeasible: TrayItem[];
  hasPlan: boolean;
}

export function slotCapacity(scenario: Scenario, slot: Slot): { capacityKg: number; trucks: number } {
  let capacityKg = 0;
  let trucks = 0;
  for (const truck of scenario.trucks) {
    if (truck.unavailable_from_slot !== null && truck.unavailable_from_slot <= slot.index) continue;
    capacityKg += truck.capacity_kg;
    trucks += 1;
  }
  return { capacityKg, trucks };
}

function trayItem(decision: Decision, response: PlanResponse): TrayItem {
  return {
    batchId: decision.batch_id,
    commodity: decision.commodity_name,
    kg: decision.kg,
    shelfH: decision.plan_shelf_h,
    holdCode: decision.hold_code,
    reason: response.reasons[decision.batch_id]?.headline ?? "",
  };
}

export function buildBoard(scenario: Scenario, response: PlanResponse | null): BoardModel {
  const slots = scenario.slots.toSorted((a, b) => a.index - b.index);
  const commodityName = new Map(scenario.commodities.map((c) => [c.id, c.name]));
  const batchById = new Map(scenario.batches.map((b) => [b.id, b]));
  const decisionById = new Map((response?.decisions ?? []).map((d) => [d.batch_id, d]));
  const dispatched = new Set(scenario.controls.dispatched.map((d) => `${d.batch_id}@${d.slot_id}`));
  const plan = response?.lading.plan ?? null;

  const loadBySlot = new Map<string, number>();
  const trucksBySlot = new Map<string, number>();
  for (const trip of plan?.trips ?? []) {
    loadBySlot.set(trip.slot_id, (loadBySlot.get(trip.slot_id) ?? 0) + trip.load_kg);
    trucksBySlot.set(trip.slot_id, (trucksBySlot.get(trip.slot_id) ?? 0) + 1);
  }

  const cardsByCell = new Map<string, CardModel[]>();
  const legSeen = new Map<string, number>();
  const cardsBySlot = new Map<string, number>();
  for (const shipment of plan?.shipments ?? []) {
    const decision = decisionById.get(shipment.batch_id);
    const batch = batchById.get(shipment.batch_id);
    const legIndex = legSeen.get(shipment.batch_id) ?? 0;
    legSeen.set(shipment.batch_id, legIndex + 1);
    const inOrder = decision?.legs[legIndex];
    const leg =
      inOrder?.slot_id === shipment.slot_id ? inOrder : decision?.legs.find((l) => l.slot_id === shipment.slot_id);
    const totalKg = decision?.kg ?? batch?.kg ?? shipment.kg;
    const card: CardModel = {
      key: `${shipment.batch_id}#${legIndex}`,
      batchId: shipment.batch_id,
      commodity: decision?.commodity_name ?? commodityName.get(batch?.commodity_id ?? "") ?? "",
      kg: shipment.kg,
      totalKg,
      split: (decision?.legs.length ?? 1) > 1 || shipment.kg < totalKg - 0.01,
      saleH: leg?.sale_h ?? null,
      marginH: leg?.margin_h ?? null,
      shelfH: leg ? leg.sale_h + leg.margin_h : null,
      discount: shipment.discount,
      locked: shipment.locked,
      dispatched: dispatched.has(`${shipment.batch_id}@${shipment.slot_id}`),
      marketId: shipment.market_id,
      slotId: shipment.slot_id,
    };
    const cellKey = `${shipment.market_id}|${shipment.slot_id}`;
    const cell = cardsByCell.get(cellKey);
    if (cell) cell.push(card);
    else cardsByCell.set(cellKey, [card]);
    cardsBySlot.set(shipment.slot_id, (cardsBySlot.get(shipment.slot_id) ?? 0) + 1);
  }

  let lastUsedIndex = -1;
  for (const slot of slots) {
    if ((cardsBySlot.get(slot.id) ?? 0) > 0) lastUsedIndex = Math.max(lastUsedIndex, slot.index);
  }

  const columns: ColumnModel[] = slots.map((slot) => {
    const { capacityKg, trucks } = slotCapacity(scenario, slot);
    const cardCount = cardsBySlot.get(slot.id) ?? 0;
    return {
      slot,
      loadKg: loadBySlot.get(slot.id) ?? 0,
      capacityKg,
      trucksAvailable: trucks,
      trucksUsed: trucksBySlot.get(slot.id) ?? 0,
      cardCount,
      collapsed: plan !== null && cardCount === 0 && slot.index > lastUsedIndex,
      departed: slot.index < scenario.policy.current_slot,
    };
  });

  const rows: RowModel[] = scenario.markets.map((market) => {
    const cells = new Map<string, CardModel[]>();
    let cardCount = 0;
    let kg = 0;
    for (const slot of slots) {
      const cards = (cardsByCell.get(`${market.id}|${slot.id}`) ?? []).toSorted(
        (a, b) => (a.marginH ?? Infinity) - (b.marginH ?? Infinity),
      );
      cells.set(slot.id, cards);
      cardCount += cards.length;
      for (const card of cards) kg += card.kg;
    }
    return { market, cells, cardCount, kg };
  });

  const held: TrayItem[] = [];
  const infeasible: TrayItem[] = [];
  if (response) {
    for (const decision of response.decisions) {
      if (decision.hold_code === "INFEASIBLE_DEMAND" || decision.status === "infeasible") {
        infeasible.push(trayItem(decision, response));
      } else if (decision.status === "held") {
        held.push(trayItem(decision, response));
      }
    }
  }
  held.sort((a, b) => a.shelfH - b.shelfH);
  infeasible.sort((a, b) => a.shelfH - b.shelfH);

  return { columns, rows, held, infeasible, hasPlan: plan !== null };
}

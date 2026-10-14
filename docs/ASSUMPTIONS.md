# Assumptions

Every number the generator draws lives in [`scenarios/assumptions.json`](../scenarios/assumptions.json). This page mirrors it with units. All of it is synthetic. Hub and mandi names are real places so the board is legible, but no price, travel time, shelf life or demand figure here is a measured fact. A test (`scenarios/test_scenarios.py`) fails if a key in the JSON is missing from this page.

## Planning window and policy

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `horizon_h` | 48 | h | Planning window. Undispatched stock that expires inside it is spoiled at the hub. Stock that outlives it carries over unsold, at no cost. |
| `slot_interval_h` | 6 | h | Gap between dispatch slots. |
| `n_slots` | 8 | slots | Slots at 0, 6, ..., 42 h (shown as D1 06:00 to D2 12:00). |
| `safety_margin_h` | 2 | h | Stock must be sale-ready at least this long before it expires. Applies to every arm and the validator. |
| `turnaround_buffer_h` | 2 | h | Loading plus unloading added to a truck's round trip (2 x travel + buffer). |
| `discount_levels` | 0, 10, 20, 30 | % | Price ladder. One price per commodity per market. |

## Inventory

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `batch_count` | 25-60 | batches | Batches on the hub floor at t=0. |
| `batch_kg` | 200-2,000 | kg | Batch size, uniform. |
| `batch_kg_step` | 50 | kg | Batch sizes are multiples of this. |
| `arrived_h_ago` | 0-36 | h | Time since arrival at the hub, uniform, independent of shelf life (harvest dates differ). FIFO sorts on it. |

## Commodities

Shelf life is the remaining hours at t=0, drawn uniformly from the range. Realized shelf life is `estimate x (1 + sigma x Z)`, Z standard normal, clipped to 0.4-1.6x.

| Commodity | Share of batches | Remaining shelf life (h) | Realized sigma | Purchase (INR/kg) | Base price (INR/kg) | Elasticity |
|---|---|---|---|---|---|---|
| Leafy greens | `leafy_greens.share` 0.20 | `leafy_greens.shelf_life_h` 8-40 | `leafy_greens.shelf_life_sigma` 0.15 | `leafy_greens.purchase_inr_per_kg` 18 | `leafy_greens.base_price_inr_per_kg` 32 | `leafy_greens.elasticity` 1.2 |
| Tomato | `tomato.share` 0.30 | `tomato.shelf_life_h` 16-110 | `tomato.shelf_life_sigma` 0.12 | `tomato.purchase_inr_per_kg` 14 | `tomato.base_price_inr_per_kg` 24 | `tomato.elasticity` 1.5 |
| Banana | `banana.share` 0.20 | `banana.shelf_life_h` 30-140 | `banana.shelf_life_sigma` 0.10 | `banana.purchase_inr_per_kg` 20 | `banana.base_price_inr_per_kg` 32 | `banana.elasticity` 1.0 |
| Mango | `mango.share` 0.15 | `mango.shelf_life_h` 40-190 | `mango.shelf_life_sigma` 0.10 | `mango.purchase_inr_per_kg` 48 | `mango.base_price_inr_per_kg` 78 | `mango.elasticity` 1.8 |
| Onion | `onion.share` 0.15 | `onion.shelf_life_h` 200-900 | `onion.shelf_life_sigma` 0.05 | `onion.purchase_inr_per_kg` 16 | `onion.base_price_inr_per_kg` 24 | `onion.elasticity` 0.6 |

Demand uplift from a discount d is `base demand x (1 + elasticity x d)`. A 30% tomato discount lifts demand 45%.

## Markets, transport and handling

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `market_count` | 4-6 | markets | Markets picked per scenario from the hub's list. |
| `transport_inr_per_kg_base` | 0.30 | INR/kg | Fixed part of freight. |
| `transport_inr_per_kg_per_h` | 0.20 | INR/kg/h | Freight per hour of forecast travel. |
| `handling_h` | 1-4 | h | Unload and auction time at the market, in 0.5 h steps. |
| `handling_inr_per_kg` | 0.60-1.20 | INR/kg | Handling charge at the market. |
| `price_jitter` | 0.08 | fraction | Market price = base x city factor x (1 +/- up to 8%). |
| `offer_drop_probability` | 0.10 | probability | Chance a market doesn't buy a given commodity that day. |
| `demand_to_stock_ratio` | 0.7-1.1 | ratio | Total forecast demand per commodity relative to stock on the floor. Below 1 means some stock can't sell at list price. |

Hubs and their markets (travel hours and city price factors are assumptions):

- Nashik hub: Mumbai Vashi 5 h (1.30), Pune Gultekdi 5 h (1.20), Surat 6 h (1.15), Indore 8 h (1.10), Ahmedabad 10 h (1.22), Nagpur 12 h (1.08), Hyderabad 13 h (1.28), Delhi Azadpur 22 h (1.45).
- Kolar hub: Bengaluru KR Market 2 h (1.15), Mysuru 4 h (1.05), Chennai Koyambedu 5 h (1.28), Coimbatore 6 h (1.12), Hyderabad 9 h (1.25), Kochi 11 h (1.35), Mumbai Vashi 16 h (1.45).

## Trucks

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `truck_count` | 2-4 | trucks | Trucks at the hub. |
| `truck_capacities_kg` | 5,000 / 7,500 / 10,000 | kg | Capacity per truck, one picked per truck. A truck serves one market per trip. |

## Uncertainty used in execution

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `demand_sigma` | 0.20 | fraction | Realized demand = forecast x (1 + 0.20 x Z), clipped to 0.2-2.0x. |
| `travel_delay_median_frac` | 0.08 | fraction | Median realized delay as a share of forecast travel time. |
| `travel_delay_sigma_log` | 0.60 | log-space sd | Delay fraction is lognormal, so delays are right-skewed. P90 delay is 0.08 x e^(1.2816 x 0.6) = 17% of travel time. |

Lading-robust plans on P10 shelf life (`estimate x (1 - 1.2816 x sigma)`) and P90 travel time (`travel x (1 + P90 delay fraction)`), both derived from the disclosed values above, which every arm can see.

## Scenario families

| Family | Meaning |
|---|---|
| `base` | No shock. Realized world drawn from the disclosed distributions. |
| `demand_shock` | Realized demand at the highest-paying market falls to `demand_shock_factor` = 50% of forecast. Unknown at plan time. |
| `route_delay` | One route takes `route_delay_extra_h` = 8 extra hours on every trip. Unknown at plan time. |
| `truck_loss` | The largest truck breaks down from slot `truck_loss_from_slot` = 2 onward. Unknown at plan time. |
| `wide_shelf` | Shelf-life sigma is multiplied by `wide_shelf_sigma_factor` = 2.5. Disclosed to every arm. |
| `healthy` | Control P2: shelf life x3 + 100 h, four 10 t trucks, demand 1.6-1.8x stock. |
| `infeasible` | Control P3: three extra leafy-green batches with 3 h of shelf life, which no market can receive fresh. |

## Accounting

- Net INR = sales revenue - transport - handling - purchase value of spoiled kg. Discount given up is reported as its own line and is already netted out of revenue.
- Spoiled kg = expired in transit + expired at the hub inside the horizon + delivered but unsold. Unsold consignment at a mandi is treated as lost, because the hub doesn't haul it back.
- Demand filled % = kg sold up to each market's realized undiscounted demand, over total realized undiscounted demand. Extra demand created by a discount isn't counted as demand filled.

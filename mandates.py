"""Riksdag seat allocation computed from Valmyndigheten's preliminary vote counts.

On election night Valmyndigheten publishes the inputs (votes per party per constituency, fixed
seats per constituency and the thresholds) but not the resulting seats. This follows the Elections
Act (vallagen 14 kap.): the modified odd-number method with first divisor 1.2 for the 310 fixed
constituency seats and for the national allocation of all 349, the 4 % national and 12 %
constituency thresholds, and the overhang rule. Ties that the law settles by lot are broken by
list order instead.
"""

FIRST_DIVISOR = 1.2


def odd_number_method(votes, seats):
    """Distributes `seats` among {party: votes} using the divisors 1.2, 3, 5, 7, …"""
    won = dict.fromkeys(votes, 0)
    if not any(votes.values()):
        return won
    for _ in range(seats):
        best = max(votes, key=lambda p: votes[p] / (FIRST_DIVISOR if won[p] == 0 else 2 * won[p] + 1))
        won[best] += 1
    return won


def party_votes(area, previous):
    field = "antalRosterForegaendeVal" if previous else "antalRoster"
    roster = area["rostfordelning"]["rosterPaverkaMandat"]
    return {p["partiforkortning"]: p.get(field) or 0 for p in roster["partiRoster"]}, roster.get(field) or 0


def allocate(data, previous=False):
    """Returns {party: {"seats", "fixed"}} for this election, or for the previous one with previous=True."""
    country = data["valomrade"]
    suffix = "ForegaendeVal" if previous else ""
    national, national_total = party_votes(country, previous)
    if not national_total:
        return {}
    above = {p for p, n in national.items() if n / national_total >= country["valomradessparrProcent"] / 100}

    fixed = dict.fromkeys(national, 0)
    for krets in country["valkretsLista"]:
        votes, krets_total = party_votes(krets, previous)
        eligible = {p: n for p, n in votes.items()
                    if n and (p in above or n / krets_total >= country["valkretssparrProcent"] / 100)}
        for party, won in odd_number_method(eligible, krets[f"totaltAntalFastaMandat{suffix}"]).items():
            fixed[party] = fixed.get(party, 0) + won

    # Fixed seats won through the 12 % rule by parties under 4 % come off the national total
    seats_left = country[f"totaltAntalMandat{suffix}"] - sum(n for p, n in fixed.items() if p not in above)
    pool = [p for p in national if p in above]
    while True:
        shares = odd_number_method({p: national[p] for p in pool}, seats_left)
        overhang = [p for p in pool if fixed[p] > shares[p]]
        if not overhang:
            break
        # A party with more fixed seats than its proportional share keeps them; the rest is redone without it
        seats_left -= sum(fixed[p] for p in overhang)
        pool = [p for p in pool if p not in overhang]

    seats = {**fixed, **shares}
    return {p: {"seats": seats.get(p, 0), "fixed": fixed.get(p, 0)} for p in national}


def summary(data):
    """Compact seat allocation for the browser, with the same method applied to the previous election."""
    country = data["valomrade"]
    now = allocate(data)
    before = allocate(data, previous=True)
    return {
        "updated": data.get("senasteUppdateringstid"),
        "counted": country.get("antalValdistriktRaknade"),
        "total": country["totaltAntalMandat"],
        "majority": country["totaltAntalMandat"] // 2 + 1,
        "parties": {p: {**s, "seats2022": before.get(p, {}).get("seats")} for p, s in now.items()},
    }

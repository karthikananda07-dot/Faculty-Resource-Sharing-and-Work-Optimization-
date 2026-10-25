
from ortools.sat.python import cp_model


def optimize_substitutes(affected_slots, faculty, weekly_hours):
    """
    Recommend substitutes for classes affected by an absence.

    Each slot must contain:
      period, class_name, subject, available_substitutes

    weekly_hours maps faculty IDs to their current weekly teaching hours.
    """
    if not affected_slots:
        return []

    model = cp_model.CpModel()
    choices = {}
    candidates_by_slot = []

    # Build the eligible candidates for each affected class.
    for i, slot in enumerate(affected_slots):
        subject = (slot.get("subject") or "").strip().casefold()

        eligible = []
        for candidate in slot.get("available_substitutes", []):
            candidate_subject = (
                candidate.get("subject") or ""
            ).strip().casefold()

            # Require a matching subject.
            if subject and candidate_subject == subject:
                eligible.append(candidate)

        candidates_by_slot.append(eligible)

        for candidate in eligible:
            fid = candidate["id"]
            choices[i, fid] = model.NewBoolVar(
                f"slot_{i}_faculty_{fid}"
            )

        # A class receives at most one substitute.
        # It may remain uncovered if nobody is eligible.
        model.Add(
            sum(choices[i, c["id"]] for c in eligible) <= 1
        )

    # A faculty member cannot cover two affected classes
    # in the same period.
    periods = {slot["period"] for slot in affected_slots}
    for period in periods:
        period_indices = [
            i for i, slot in enumerate(affected_slots)
            if slot["period"] == period
        ]

        faculty_ids = {
            candidate["id"]
            for i in period_indices
            for candidate in candidates_by_slot[i]
        }

        for fid in faculty_ids:
            variables = [
                choices[i, fid]
                for i in period_indices
                if (i, fid) in choices
            ]
            model.Add(sum(variables) <= 1)

    # Do not exceed a substitute's remaining weekly capacity.
    for candidate in faculty:
        fid = candidate["id"]
        maximum = candidate.get("max_hours", 18)
        current = weekly_hours.get(fid, 0)

        variables = [
            variable
            for (i, candidate_id), variable in choices.items()
            if candidate_id == fid
        ]

        if variables:
            model.Add(sum(variables) + current <= maximum)

    # First maximize the number of covered classes.
    model.Maximize(sum(choices.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []

    recommendations = []
    for i, slot in enumerate(affected_slots):
        selected = None

        for candidate in candidates_by_slot[i]:
            key = (i, candidate["id"])
            if key in choices and solver.Value(choices[key]):
                selected = candidate
                break

        recommendations.append({
            "class_name": slot["class_name"],
            "subject": slot.get("subject"),
            "period": slot["period"],
            "room": slot.get("room"),
            "date": slot["date"],
            "substitute": (
                {
                    "faculty_id": selected["id"],
                    "faculty_name": selected["name"]
                }
                if selected else None
            ),
            "status": "recommended" if selected else "uncovered"
        })

    return recommendations

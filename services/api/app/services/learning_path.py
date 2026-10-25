"""Course lesson order and the learner's own completion state."""


def sequence_status(completed: list[bool]) -> list[str]:
    """A lesson opens when every earlier lesson in the same course is complete."""
    previous_complete = True
    statuses: list[str] = []
    for done in completed:
        if done:
            statuses.append("complete")
        elif previous_complete:
            statuses.append("ready")
        else:
            statuses.append("locked")
        previous_complete = done
    return statuses

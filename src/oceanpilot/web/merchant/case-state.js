// One server snapshot backs both existing case views and the bound Agent context.
function createCaseContext() {
  let caseId = null;
  let snapshot = null;
  let generation = 0;

  function select(id) {
    if (id === caseId) return false;
    caseId = id;
    snapshot = null;
    generation += 1;
    return true;
  }

  function accept(value) {
    if (!value || value.case_id !== caseId || !Number.isInteger(value.revision)) return false;
    if (snapshot && value.revision < snapshot.revision) return false;
    snapshot = value;
    return true;
  }

  function capture() {
    return {caseId, revision: snapshot ? snapshot.revision : null,
      ruleFingerprint: snapshot ? snapshot.rule_fingerprint ?? null : null, generation};
  }

  function isCurrent(ticket, includeRevision = true) {
    return ticket.caseId === caseId && ticket.generation === generation &&
      (!includeRevision || (ticket.revision === (snapshot ? snapshot.revision : null) &&
        ticket.ruleFingerprint === (snapshot ? snapshot.rule_fingerprint ?? null : null)));
  }

  return {
    select, accept, capture, isCurrent,
    get caseId() { return caseId; },
    get snapshot() { return snapshot; },
  };
}

"""Independent offline checks of clarification resolution; no provider calls."""
import json
from uuid import uuid4
from staylead_platform.domains.hospitality.schemas.guest_brief import validate_guest_brief_proposal as validate
from staylead_platform.platform.contracts.guest_brief import GuestBriefProposal as Proposal, GuestBriefSnapshot as Snapshot

def run(data, pending, ops):
 result=validate(Snapshot(1,data,tuple(pending)),Proposal(tuple(ops)))
 return {'data':result.data,'pending_fields':result.pending_fields,'delta':result.applied_delta,'status':result.status}
empty={'dates':{'check_in':None,'check_out':None,'nights':None},'party':{'adults':None,'children':[]}}
member=str(uuid4())
base={'dates':{'check_in':'2027-05-10','check_out':'2027-05-13','nights':3},'party':{'adults':2,'children':[{'member_id':member,'age':7}]}}
results={
'adults_resolution':run(empty,['party.adults'],[{'op':'set_adults','count':2}]),
'child_resolution':run(base,['party.children.member'],[{'op':'remove_child','member_id':member}]),
'known_checkin_only':run(empty,[],[{'op':'set_dates','check_in':'2027-05-10'}]),
'pending_known_age_claim':run(base,[f'party.children.{member}.age'],[]),
}
print(json.dumps(results,indent=2))

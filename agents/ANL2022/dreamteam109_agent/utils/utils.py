from geniusweb.issuevalue.Bid import Bid

def bid_to_string(bid: Bid) -> str:
    return str(dict(sorted(bid.getIssueValues().items())))

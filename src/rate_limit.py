from collections import defaultdict, deque
from datetime import datetime, timedelta
class RateLimiter:
    def __init__(self, limit=30): self.limit=limit; self.hits=defaultdict(deque)
    def allow(self,user_id,now):
        q=self.hits[user_id]; cutoff=now-timedelta(minutes=1)
        while q and q[0]<=cutoff:q.popleft()
        if len(q)>=self.limit:return False
        q.append(now); return True

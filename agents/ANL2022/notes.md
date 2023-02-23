Agents were downloaded from: https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWebThirdParties

# Agent Fish
- changes:
    - agentfish.py line 212 `newutilspace = self.profileint.getProfile()` -> `newutilspace = self.profile`
    - extend_util_space.py line 34 `self._minUtil = 0.7*range.getMax()` -> `self._minUtil = Decimal("0.7")*range.getMax()`
    - agentfish.py line 223 `time = self.progress.get(time() * 1000)` -> `time_to_deadline = self.progress.get(time() * 1000)`
    - agentfish.py line 285 decimal vs float

# BIU Agent
- changes:
    - BIU_agent.py line 203 `with open(self_dir, "w") as f:` -> `with open(f"{self.storage_dir}/data.md", "w") as f:`
    - BIU_agent.py line 190 added all()
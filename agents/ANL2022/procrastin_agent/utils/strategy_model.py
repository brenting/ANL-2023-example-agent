import numpy as np
from scipy.stats import norm

class StrategyModel():
	def __init__(self, alphas: list, betas: list, accepts: list):
		self.alphas = alphas
		self.betas = betas
		self.accepts = accepts

		self.SIGMA = 0.1
		self.LINE_FACTOR = 0.1

	def u(self, starting_util: float, alpha: float):
		return self.p(alpha) * (starting_util + (1.0 - starting_util) * alpha)

	def p(self, alpha: float):
		line_value = self.linear(alpha)
		gauss_factor = self.gauss(np.repeat(alpha, len(self.alphas)), self.alphas, self.SIGMA)
		gauss_value = np.array(self.accepts) * gauss_factor
		prob = (np.sum(gauss_value) + self.LINE_FACTOR * line_value) / (np.sum(gauss_factor) + self.LINE_FACTOR)
		return prob

	def gauss(self, x, mu, sig):
		return np.exp(-np.power((x - mu) / sig, 2.) / 2 )

	def linear(self, x: float):
		return 1.0 - x
	
	#call with mag = desired degrees of precision
	def max_u(self, starting_util: float, min_u: float, max_u: float, mag: int):
		if mag > 0:
			step = float(max_u - min_u)/10
			start = min_u
			maxi = start
			best_u = None
			while start <= max_u:
				new_u = self.u(starting_util, start)
				if best_u is None or new_u > best_u:
					maxi = start
					best_u = new_u
				start += step
			return self.max_u(starting_util, min(max_u - 2 * step, max(maxi-step, min_u)), min(max_u, max(maxi+step, min_u + 2 * step)), mag-1)
		else:
			return min_u

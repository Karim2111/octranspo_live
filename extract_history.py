"""Fetch TransSee trip history and save track/trip ID pairs to a text file."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import quote, urljoin

import httpx
from dotenv import load_dotenv


URL = (
	"https://www.transsee.ca/triplist?a=octranspo&t=adv&route=10"
	"&fromdate=2026-01-01&todate=2026-03-31&starttime=04%3A00&endtime=04%3A00"
	"&nextday=on&service=0&blockid=&tripid=&veh=&beforestart=1&mintime=0"
	"&mintravel=0.00&report=0&ok=OK"
)

OUTPUT_FILE = Path(__file__).with_name("trip_history_pairs.txt")

USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
	"AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/124.0.0.0 Safari/537.36"
)


def build_cookie_header() -> str:
	cookies = []
	for name in ("Premium", "pw170.133.246.59", "TransSet"):
		value = os.getenv(name)
		if value:
			cookies.append(f"{name}={value}")
	return "; ".join(cookies)


def solve_proof_of_work(seed: str, difficulty: int) -> str:
	prefix = "0" * difficulty
	nonce = 0

	while True:
		candidate = f"{seed}{nonce}"
		digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()
		if digest.startswith(prefix):
			return candidate
		nonce += 1


def fetch_html(client: httpx.Client, url: str) -> str:
	response = client.get(url)
	response.raise_for_status()
	return response.text


def fetch_with_challenge(client: httpx.Client, url: str) -> str:
	initial_html = fetch_html(client, url)
	challenge_match = re.search(
		r"process\('([^']+)',\s*(\d+)\).+?window\.location\.href='([^']+)&pw='\+hash;",
		initial_html,
		re.DOTALL,
	)
	if not challenge_match:
		return initial_html

	seed = challenge_match.group(1)
	difficulty = int(challenge_match.group(2))
	redirect_base = challenge_match.group(3)
	proof = solve_proof_of_work(seed, difficulty)
	final_url = urljoin(
		"https://www.transsee.ca/",
		f"{redirect_base}&pw={quote(proof)}&ua={quote(USER_AGENT)}",
	)
	return fetch_html(client, final_url)


def extract_track_trip_pairs(html: str) -> list[tuple[str, str]]:
	pairs = re.findall(
		r"trackid\s*:\s*(\d+)\s*.*?tripid\s*:\s*(\d+)",
		html,
		re.IGNORECASE | re.DOTALL,
	)
	if pairs:
		return list(dict.fromkeys(pairs))

	pairs = re.findall(
		r"trackid=(\d+)\D+tripid=(\d+)",
		html,
		re.IGNORECASE | re.DOTALL,
	)
	return list(dict.fromkeys(pairs))


def write_pairs_to_file(pairs: list[tuple[str, str]]) -> None:
	lines = [f"trackid: {track_id} tripid: {trip_id}" for track_id, trip_id in pairs]
	OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
	load_dotenv()
	headers = {"User-Agent": USER_AGENT}
	cookie_header = build_cookie_header()
	if cookie_header:
		headers["Cookie"] = cookie_header

	timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)
	with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
		html = fetch_with_challenge(client, URL)
		pairs = extract_track_trip_pairs(html)
		write_pairs_to_file(pairs)
		print(f"Saved {len(pairs)} pairs to {OUTPUT_FILE}")


if __name__ == "__main__":
	main()
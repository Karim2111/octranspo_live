
"""Fetch the Transsee triplist response for OC Transpo route 10."""

from __future__ import annotations

import hashlib
import os
import re
from html import unescape
from urllib.parse import quote, urljoin

import httpx
from dotenv import load_dotenv


URL = (
	"https://www.transsee.ca/triplist?a=octranspo&t=adv&route=10"
	"&fromdate=2026-05-08&todate=2026-05-12&starttime=04%3A00&endtime=04%3A00"
	"&nextday=on&service=0&blockid=&tripid=&veh=&beforestart=1&mintime=0"
	"&mintravel=0.00&report=1&group=0&group=7&group=8&group=16&ok=OK"
)

TRIPSTOPS_URL = "https://www.transsee.ca/tripstops?a=octranspo&id={trip_id}"

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


def extract_unique_trip_paths(html: str) -> list[str]:
	matches = re.findall(r"trippath\?a=octranspo&id=(\d+)", html)
	return list(dict.fromkeys(matches))


def extract_trip_id(html: str) -> str:
	match = re.search(r"tripsched\?a=octranspo&t=(\d+)&date=", html)
	return match.group(1) if match else ""


def strip_html(text: str) -> str:
	cleaned = re.sub(r"<[^>]+>", " ", text)
	cleaned = unescape(cleaned)
	return re.sub(r"\s+", " ", cleaned).strip()


def format_tripstops_table(html: str) -> str:
	rows = []
	for match in re.finditer(
		r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>.*?</td><td>.*?</td></tr>",
		html,
		re.DOTALL,
	):
		time_value = strip_html(match.group(1))
		stop_value = strip_html(match.group(2))
		schedule_value = strip_html(match.group(3))
		rows.append((time_value, stop_value, schedule_value))

	if not rows:
		return ""

	headers = ("Time", "Stop", "Schedule")
	widths = [
		max(len(headers[0]), *(len(row[0]) for row in rows)),
		max(len(headers[1]), *(len(row[1]) for row in rows)),
		max(len(headers[2]), *(len(row[2]) for row in rows)),
	]

	lines = [
		f"{headers[0]:<{widths[0]}} | {headers[1]:<{widths[1]}} | {headers[2]:<{widths[2]}}",
		f"{'-' * widths[0]}-+-{'-' * widths[1]}-+-{'-' * widths[2]}",
	]
	for time_value, stop_value, schedule_value in rows:
		lines.append(
			f"{time_value:<{widths[0]}} | {stop_value:<{widths[1]}} | {schedule_value:<{widths[2]}}"
		)
	return "\n".join(lines)


def fetch_tripstops_response(client: httpx.Client, trip_id: str) -> str:
	response = client.get(TRIPSTOPS_URL.format(trip_id=trip_id))
	response.raise_for_status()
	trip_id_value = extract_trip_id(response.text)
	table = format_tripstops_table(response.text)
	if trip_id_value and table:
		return f"Trip ID: {trip_id_value}\n\n{table}"
	if trip_id_value:
		return f"Trip ID: {trip_id_value}"
	return table


def fetch_final_response() -> str:
	load_dotenv()
	cookie_header = build_cookie_header()
	headers = {"User-Agent": USER_AGENT}
	if cookie_header:
		headers["Cookie"] = cookie_header

	with httpx.Client(follow_redirects=True, headers=headers, timeout=30.0) as client:
		first_response = client.get(URL)
		first_response.raise_for_status()

		challenge_match = re.search(
			r"process\('([^']+)',\s*(\d+)\).+?window\.location\.href='([^']+)&pw='\+hash;",
			first_response.text,
			re.DOTALL,
		)
		if not challenge_match:
			trip_ids = extract_unique_trip_paths(first_response.text)
			if not trip_ids:
				return ""
			return fetch_tripstops_response(client, trip_ids[0])

		seed = challenge_match.group(1)
		difficulty = int(challenge_match.group(2))
		redirect_base = challenge_match.group(3)

		proof = solve_proof_of_work(seed, difficulty)
		final_url = urljoin("https://www.transsee.ca/", f"{redirect_base}&pw={quote(proof)}&ua={quote(USER_AGENT)}")

		final_response = client.get(final_url)
		final_response.raise_for_status()
		trip_ids = extract_unique_trip_paths(final_response.text)
		if not trip_ids:
			return ""
		return fetch_tripstops_response(client, trip_ids[0])


if __name__ == "__main__":
	print(fetch_final_response())


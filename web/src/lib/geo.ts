import type { IpLocation } from '$lib/client';
import { LOCALE } from '$lib/format';

// Countries' names come from the runtime's own data (ICU), so there is no list to keep current.
const regionNames = new Intl.DisplayNames([LOCALE], { type: 'region' });

/** "Canada" from "CA"; the code itself if the runtime doesn't know it. */
export function countryName(code: string): string {
	return regionNames.of(code) ?? code;
}

// A flag emoji is the country's two letters as "regional indicator" symbols: CA is 🇨 🇦.
const REGIONAL_INDICATOR_A = 0x1f1e6;
const LETTER_A = 'A'.charCodeAt(0);

/** 🇨🇦 from "CA", an ISO 3166-1 alpha-2 code: two ASCII letters. Systems without flag emoji
 * (Windows) show the two letters instead. */
export function flag(code: string): string {
	const letters = code.toUpperCase();
	const indicator = (index: number) => REGIONAL_INDICATOR_A + letters.charCodeAt(index) - LETTER_A;
	return String.fromCodePoint(indicator(0), indicator(1));
}

/** A point on the world map: a place, how much came from it, and what to say about it. */
export interface MapPoint {
	latitude: number;
	longitude: number;
	weight: number;
	title: string;
}

/** "Toronto, Canada", as much of it as `location` knows. */
export function placeName(location: Pick<IpLocation, 'city' | 'country_code'>): string {
	return [location.city, location.country_code && countryName(location.country_code)]
		.filter(Boolean)
		.join(', ');
}

/** `location`'s own point on the map, if it has coordinates. */
export function locationPoint(location: IpLocation): MapPoint | undefined {
	if (location.latitude === null || location.longitude === null) {
		return undefined;
	}
	return {
		latitude: location.latitude,
		longitude: location.longitude,
		weight: 1,
		title: placeName(location)
	};
}

/** Public services that say more about an address: its abuse reports, open ports and scanning. */
export function lookups(address: string): { name: string; href: string }[] {
	const ip = encodeURIComponent(address);
	return [
		{ name: 'AbuseIPDB', href: `https://www.abuseipdb.com/check/${ip}` },
		{ name: 'GreyNoise', href: `https://viz.greynoise.io/ip/${ip}` },
		{ name: 'Shodan', href: `https://www.shodan.io/host/${ip}` },
		{ name: 'ipinfo', href: `https://ipinfo.io/${ip}` }
	];
}

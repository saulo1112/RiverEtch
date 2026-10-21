// Every string of the "Request a study reach" form. A preview: nothing entered leaves the page.

/** Purposes a request can name, in display order. */
export const PURPOSES = [
  "Permit oversight",
  "Drought and flood monitoring",
  "Research",
  "Other",
] as const;

/** Answers to "Is in-situ water data available for this reach?". */
export const IN_SITU_ANSWERS = ["Yes", "No", "Not sure"] as const;

/** Labels, hints and messages of the request form. */
export const REQUEST = {
  card: {
    title: "Request a study reach",
    text: "Propose a river reach to observe.",
  },
  heading: "Request a study reach",
  back: "Back",
  backLabel: "Back to your cases",
  demoOnly: "In this preview, requests stay on this page.",
  required: "Required",
  optional: "Optional",
  fields: {
    reachName: { label: "Reach name", hint: "A short name, e.g. the towns at each end." },
    river: { label: "River or water body" },
    location: { label: "Location", hint: "Place names or landmarks that find the reach." },
    coordinates: { legend: "Coordinates", hint: "Decimal degrees, both or neither." },
    latitude: { label: "Latitude" },
    longitude: { label: "Longitude" },
    purpose: { label: "Purpose", placeholder: "Choose a purpose" },
    inSitu: { legend: "Is in-situ water data available for this reach?" },
    notes: { label: "Notes" },
  },
  submit: "Submit request",
  errors: {
    summary: (count: number) =>
      count === 1
        ? "There is 1 problem with the request"
        : `There are ${String(count)} problems with the request`,
    reachName: "Enter a name for the reach.",
    river: "Enter the river or water body.",
    latitudeNumber: "Enter the latitude as a number between −90 and 90.",
    longitudeNumber: "Enter the longitude as a number between −180 and 180.",
    latitudeMissing: "Enter a latitude too, or clear the longitude.",
    longitudeMissing: "Enter a longitude too, or clear the latitude.",
    purpose: "Choose a purpose.",
    inSitu: "Choose whether in-situ water data is available.",
  },
  confirmation: {
    heading: "Your request",
    summaryLabel: "Your request",
    coordinates: "Coordinates",
    none: "Not given",
    body: "The full version of RiverEtch will let you request and order study reaches, depending on availability and the RiverEtch team's earlier research on each river.",
    again: "Request another",
    back: "Back to your cases",
  },
  announceOpen: "Request a study reach. In this preview, requests stay on this page.",
  announceDone: "Your request is shown. In this preview it is not sent.",
} as const;

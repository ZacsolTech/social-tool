import type { ClipAspect } from "./clips";
import type { LengthId } from "./clipsCore";
import type { Faq } from "./content";
import { SITE } from "./site";

/** What a landing page pre-selects in the clips tool. */
export type ClipPreset = { length?: LengthId; aspect?: ClipAspect; style?: string; language?: string };

export type ClipPage = {
  slug: string;
  nav: string;
  title: string;
  h1: string;
  highlight: string;
  description: string;
  intro: string;
  preset: ClipPreset;
  howTo: string[];
  tips: { title: string; body: string }[];
  faqs: Faq[];
};

export const CLIPS_SLUG = "ai-clip-generator";

const common: Faq[] = [
  {
    q: "How does the AI pick the clips?",
    a: "It listens to the whole video, writes down every word with its timing, then reads the transcript like an experienced short-form editor. It looks for moments that open with a hook, make sense on their own and end on a payoff, and scores each one on hook, flow, value and shareability. Every clip starts and ends on a full sentence, never mid-word.",
  },
  {
    q: "Is it free? Is there a watermark?",
    a: `Yes, ${SITE.name} AI Clips is free with no sign-up and no watermark (a small credit is optional and off by default). A fair daily limit keeps it fast for everyone.`,
  },
  {
    q: "How long can my video be?",
    a: "Up to 90 minutes per project and 1 GB per upload. For a longer video, set a start and end time to search only the part you want. Podcasts, interviews, lectures, streams and vlogs all work well.",
  },
  {
    q: "Can I change what the AI chose?",
    a: "Yes. Every clip has an editor: move the start or end by a sentence or to an exact time, rewrite the hook title, change the caption style or turn captions off, and switch between 9:16, 1:1, 4:5 or the original shape. Only that clip is re-rendered. You can also search again with another clip length or a topic, without waiting for the AI to listen again.",
  },
  {
    q: "Which languages work?",
    a: "Over 40, including English, Urdu, Roman Urdu, Hindi, Hinglish, Arabic, Bengali, Punjabi, Spanish and Indonesian. Captions are drawn in the right script (Nastaliq for Urdu, right-to-left for Arabic), and titles and hashtags are written in your video's language.",
  },
  {
    q: "What happens to my video?",
    a: "It's used only to make your clips and is deleted automatically within 24 hours. Videos are never shared, listed publicly or used to train AI. For picking moments only the transcript text is sent to the AI, never the video. Details in our privacy policy.",
  },
];

const steps = (first: string): string[] => [
  first,
  "Pick a clip length (or Auto) and the look: vertical 9:16 with the speaker followed, captions on, a hook title. Press Find viral clips.",
  "Watch the clips as they're made, best first. Tweak any clip, then download one by one or all at once as a ZIP with titles and hashtags.",
];

export const CLIP_PAGES: ClipPage[] = [
  {
    slug: CLIPS_SLUG,
    nav: "AI clip generator",
    title: "AI Clip Generator: Turn Long Videos Into Viral Shorts, Free",
    h1: "Turn one long video into viral clips",
    highlight: "viral clips",
    description:
      "Free AI clip generator: upload a podcast, interview or YouTube video and get the best moments as vertical Shorts, Reels and TikToks with captions, hook titles and a virality score. No watermark.",
    intro:
      "Upload a long video or paste a link. AI finds the moments people will watch to the end, cuts them on full sentences, follows the speaker in 9:16, adds animated captions and a hook, and scores each clip. Ready to post.",
    preset: {},
    howTo: steps("Upload a long video (MP4, MOV, WebM) or paste a YouTube, Facebook, Instagram or X link."),
    tips: [
      { title: "Hooks first", body: "Clips that hook in the first 3 seconds get watched. The AI favours openings with a question, a bold claim or a surprise, and tells you why." },
      { title: "Never mid-sentence", body: "Every clip starts and ends on a sentence edge with a breath of room, so nothing sounds chopped." },
      { title: "One link, a week of posts", body: "A 30-minute podcast usually gives 6 to 10 good clips. Download them all as a ZIP with titles and hashtags." },
    ],
    faqs: [
      { q: "How do I turn a long video into Shorts for free?", a: "Upload it above (or paste its link), press Find viral clips and wait a few minutes. The clips appear one by one, best first, already vertical and captioned. Download them or tweak any one in the editor." },
      ...common,
    ],
  },
  {
    slug: "youtube-video-to-shorts",
    nav: "YouTube to Shorts",
    title: "YouTube Video to Shorts: AI Turns Long Videos Into Shorts, Free",
    h1: "Turn YouTube videos into Shorts",
    highlight: "Shorts",
    description:
      "Paste a YouTube link and AI cuts the best moments into vertical YouTube Shorts with captions, hook titles and a virality score. Free, no watermark, no sign-up.",
    intro: "Your long videos already contain dozens of Shorts. Paste the link, and AI finds them, frames them for 9:16 and captions them, so your channel gets daily Shorts without extra filming.",
    preset: { length: "medium" },
    howTo: steps("Paste your YouTube video link, or upload the file you exported."),
    tips: [
      { title: "Shorts sweet spot", body: "30 to 60 seconds gives a complete thought and a strong finish. Change it to under 30 s for faster loops." },
      { title: "Speaker always in frame", body: "Smart Reframe follows whoever is talking and switches between people, so nothing important falls off the edge." },
      { title: "Titles included", body: "Every clip comes with a title, a description and hashtags you can paste straight into YouTube." },
    ],
    faqs: common,
  },
  {
    slug: "podcast-to-clips",
    nav: "Podcast clips",
    title: "Podcast to Clips: AI Finds the Best Podcast Moments for Reels & TikTok",
    h1: "Your podcast, cut into clips that travel",
    highlight: "clips that travel",
    description:
      "Upload a video podcast and AI finds the best moments, frames both speakers for vertical video and adds captions. Get Reels, TikToks and Shorts in minutes. Free.",
    intro: "Upload an episode. AI listens to the whole conversation, picks the moments with a hook and a payoff, keeps the person talking in frame (or both, in split screen), and captions every word.",
    preset: { length: "long", style: "podcast" },
    howTo: steps("Upload your video podcast episode, or paste a YouTube link to it."),
    tips: [
      { title: "Two people? Split screen", body: "When both hosts react, Smart Reframe stacks them top and bottom. Otherwise it follows whoever is talking." },
      { title: "Search by topic", body: "Type a topic (\"money\", \"relationships\") and AI only returns clips about it." },
      { title: "Up to 90 minutes", body: "Long episodes are welcome. Pick a start and end to search only one segment." },
    ],
    faqs: common,
  },
  {
    slug: "long-video-to-short-clips",
    nav: "Long to short",
    title: "Long Video to Short Clips: Free AI Video Clipper Online",
    h1: "Long video in, short clips out",
    highlight: "short clips out",
    description:
      "Cut long videos into short clips automatically. AI finds highlights, reframes to vertical and adds captions. Lectures, streams, webinars and vlogs. Free online, no watermark.",
    intro: "Stop scrubbing through hours of footage. AI finds the highlights in your lecture, livestream, webinar or vlog and cuts them into short, captioned clips with titles.",
    preset: {},
    howTo: steps("Upload your long video or paste its link."),
    tips: [
      { title: "Any length you want", body: "From punchy 15-second loops to 3-minute stories: pick the length, the AI fits the moments to it." },
      { title: "Square and 4:5 too", body: "Make vertical, square or feed-sized clips, or keep the original shape for LinkedIn and X." },
      { title: "Clean cuts", body: "Optionally remove \"um\"s and long pauses so every clip moves fast." },
    ],
    faqs: common,
  },
  {
    slug: "video-to-reels",
    nav: "Video to Reels",
    title: "Video to Reels: AI Makes Instagram Reels From Your Long Videos, Free",
    h1: "Make Instagram Reels from any long video",
    highlight: "Instagram Reels",
    description:
      "Turn long videos into Instagram Reels automatically: AI picks the moments, frames them 9:16, adds trending caption styles and a hook. Free, no watermark.",
    intro: "Reels reward consistency. Turn one video into a week of Reels: AI picks the moments, frames them for the Reels screen (clear of the buttons), and adds the caption style people stop for.",
    preset: { length: "short", style: "highlight-box" },
    howTo: steps("Upload your video or paste a Facebook, Instagram or YouTube link."),
    tips: [
      { title: "Safe from the buttons", body: "Faces and captions stay clear of the Reels like, comment and share buttons." },
      { title: "Hook on screen", body: "A bold hook title sits at the top for the first seconds, the trick top creators use." },
      { title: "Caption styles", body: "Pick from 14 styles, or open any clip in the full caption editor for word-by-word control." },
    ],
    faqs: common,
  },
  {
    slug: "urdu-hindi-video-to-shorts",
    nav: "Urdu & Hindi clips",
    title: "Urdu & Hindi Video to Shorts: AI Clips With Urdu, Roman Urdu & Hindi Captions",
    h1: "Shorts from Urdu & Hindi videos, done right",
    highlight: "done right",
    description:
      "AI finds the best moments in Urdu, Hindi and Punjabi podcasts and videos and turns them into Shorts with Nastaliq Urdu, Roman Urdu or Hindi captions. Free, no watermark.",
    intro: "Big clipping apps struggle with Urdu and Hindi. Here the AI understands your language, writes titles and hashtags in it, and captions in proper Nastaliq, Roman Urdu or Devanagari.",
    preset: { language: "ur" },
    howTo: steps("Upload your Urdu, Hindi or Punjabi video, or paste its link. Pick the language (Roman Urdu for Latin letters)."),
    tips: [
      { title: "Roman Urdu captions", body: "Choose Roman Urdu or Hinglish and captions come out the way people type them: \"kya haal hai\"." },
      { title: "Titles in your language", body: "Hooks, titles and hashtags are written in the language of the video, not translated English." },
      { title: "Desi styles", body: "Caption styles like Desi Bold and Match Day were made for South Asian audiences." },
    ],
    faqs: common,
  },
];

export const clipPageBySlug = (slug: string) => CLIP_PAGES.find((p) => p.slug === slug);

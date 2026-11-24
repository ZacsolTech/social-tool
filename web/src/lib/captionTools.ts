import type { Faq } from "./content";
import { SITE } from "./site";

/** What a landing page pre-selects in the caption tool. */
export type CaptionPreset = { language?: string; style?: string; srt?: boolean };

export type CaptionPage = {
  slug: string;
  nav: string;
  title: string;
  h1: string;
  highlight: string;
  description: string;
  intro: string;
  preset: CaptionPreset;
  howTo: string[];
  tips: { title: string; body: string }[];
  faqs: Faq[];
};

export const CAPTIONS_SLUG = "auto-caption-generator";

const common: Faq[] = [
  {
    q: "Is it really free?",
    a: `Yes. ${SITE.name} Captions is free with no sign-up and no watermark (a small credit is optional and you can turn it off). A fair daily limit keeps it fast for everyone.`,
  },
  {
    q: "Which languages work?",
    a: "Over 40 languages, including English, Urdu, Roman Urdu, Hindi, Hinglish, Arabic, Bengali, Punjabi, Spanish, Portuguese, French, Indonesian and Turkish. Urdu is drawn in proper Nastaliq, and right-to-left captions keep their word order.",
  },
  {
    q: "How accurate are the captions?",
    a: "Very accurate for clear speech. Every word is editable before you export: tap a line, fix it, and the timing stays in sync. Adding names or special words under More options helps the AI spell them right.",
  },
  {
    q: "What happens to my video?",
    a: "It's used only to make your captions and is deleted automatically within 24 hours. Videos are never shared, listed publicly or used to train AI. The sound is turned into text by speech recognition, and for AI translation or highlights only the caption text is sent, never the video. Details in our privacy policy.",
  },
  {
    q: "Can I download subtitles without burning them in?",
    a: "Yes. Download SRT, VTT or plain text at any time, free and without a watermark, to upload to YouTube, Facebook or your editor.",
  },
];

const steps = (first: string): string[] => [
  first,
  "Pick the language (or let it detect), and press Generate captions. The AI writes every word with its timing.",
  "Fix any word, choose a style, add a hook title or emojis, then export the MP4 or download SRT.",
];

export const CAPTION_PAGES: CaptionPage[] = [
  {
    slug: CAPTIONS_SLUG,
    nav: "Auto captions",
    title: "Auto Caption Generator: Free AI Captions for Videos (Urdu, Hindi, English)",
    h1: "Add captions to any video, automatically",
    highlight: "automatically",
    description:
      "Free AI auto captions for TikTok, Reels and Shorts. Word-by-word highlights, emojis, hook titles, Urdu, Roman Urdu, Hindi and 40+ languages. No sign-up, no watermark.",
    intro:
      "Upload a video or paste a link. AI writes every word with perfect timing, then you style it like the top creators: word-by-word highlights, emojis, a hook title and a progress bar. Export the MP4 or SRT.",
    preset: {},
    howTo: steps("Upload your video (MP4, MOV, WebM) or paste a TikTok, Instagram, Facebook or YouTube link."),
    tips: [
      { title: "Captions that keep people watching", body: "Most people watch with the sound off. Bold, word-by-word captions keep them reading, and watching, longer." },
      { title: "Your language, done right", body: "Urdu in Nastaliq, Roman Urdu, Hindi, Hinglish and Arabic that reads right-to-left. Big caption apps get these wrong." },
      { title: "Fix anything in seconds", body: "Edit words like a document. Enter splits a line, timing stays in sync, and Undo is always there." },
    ],
    faqs: [
      { q: "How do I add captions to a video for free?", a: "Upload the video above, press Generate captions, pick a style and press Export video. It takes about a minute for a short clip." },
      ...common,
    ],
  },
  {
    slug: "add-urdu-subtitles-to-video",
    nav: "Urdu subtitles",
    title: "Add Urdu Subtitles to Video: Free Urdu Caption Generator (Nastaliq)",
    h1: "Urdu subtitles, written beautifully",
    highlight: "written beautifully",
    description:
      "Automatically add Urdu subtitles to any video, drawn in proper Nastaliq script with correct right-to-left order. Edit, style and download MP4 or SRT. Free.",
    intro:
      "Speak Urdu, get Urdu captions in elegant Nastaliq, with English words mixed in drawn in English. Prefer Roman Urdu? One tap converts the captions to English letters.",
    preset: { language: "ur", style: "desi-bold" },
    howTo: steps("Upload your Urdu video or paste its link."),
    tips: [
      { title: "Real Nastaliq", body: "Captions use Noto Nastaliq Urdu, the script Urdu readers expect, not a squashed Arabic font." },
      { title: "Right-to-left that works", body: "Word order stays correct even with highlights, emojis and English words in the same line." },
      { title: "Roman Urdu in one tap", body: "Switch the whole video to Roman Urdu (“kya haal hai”) without typing it again." },
    ],
    faqs: common,
  },
  {
    slug: "roman-urdu-caption-generator",
    nav: "Roman Urdu captions",
    title: "Roman Urdu Caption Generator: Auto Subtitles in Roman Urdu",
    h1: "Roman Urdu captions, automatically",
    highlight: "automatically",
    description:
      "Turn Urdu speech into Roman Urdu captions (kya haal hai) the way people type on social media. Word-by-word highlights, emojis, free MP4 and SRT download.",
    intro:
      "Most Pakistani creators write captions in Roman Urdu. We listen to your Urdu and write it in English letters, word by word, with perfect timing. No typing.",
    preset: { language: "ur-Latn", style: "bold-pop" },
    howTo: steps("Upload your video or paste a TikTok, Instagram, Facebook or YouTube link."),
    tips: [
      { title: "Spelled like people type", body: "“bohat”, “zindagi”, “InshaAllah”: familiar spellings your audience reads instantly." },
      { title: "Also English translation", body: "Add English captions under the Roman Urdu to reach viewers outside Pakistan." },
      { title: "Made for Reels & Shorts", body: "Pick a preset like Bold Pop or Match Day and you're ready to post." },
    ],
    faqs: common,
  },
  {
    slug: "hindi-subtitle-generator",
    nav: "Hindi & Hinglish",
    title: "Hindi Subtitle Generator: Auto Hindi & Hinglish Captions for Videos",
    h1: "Hindi and Hinglish captions in a minute",
    highlight: "in a minute",
    description:
      "Auto-generate Hindi subtitles in Devanagari or Hinglish (Roman Hindi). Highlights, emojis and hook titles for Reels and Shorts. Free, no watermark.",
    intro: "Get Hindi captions in Devanagari, or Hinglish in English letters. Style them, add emojis and a hook, and export.",
    preset: { language: "hi" },
    howTo: steps("Upload your Hindi video or paste its link."),
    tips: [
      { title: "Devanagari or Hinglish", body: "Choose the script your audience reads. Switch any time with one tap." },
      { title: "Mixed Hindi-English", body: "English words stay in English letters, inside your Hindi captions." },
      { title: "Translate to English", body: "Add English captions underneath to grow beyond India." },
    ],
    faqs: common,
  },
  {
    slug: "arabic-subtitles-generator",
    nav: "Arabic captions",
    title: "Arabic Subtitles Generator: Auto Arabic Captions, Right-to-Left Done Right",
    h1: "Arabic captions that read right",
    highlight: "read right",
    description:
      "Automatic Arabic subtitles with correct right-to-left order, highlights and emojis. Download MP4 or SRT. Free, no sign-up.",
    intro: "Arabic speech becomes clean Arabic captions in Naskh script, right-to-left, even with word highlights and emojis.",
    preset: { language: "ar", style: "desi-bold" },
    howTo: steps("Upload your Arabic video or paste its link."),
    tips: [
      { title: "Correct word order", body: "Highlights and emojis never scramble right-to-left text." },
      { title: "Translate both ways", body: "Add English captions under Arabic, or the other way round." },
      { title: "SRT for YouTube", body: "Download the subtitle file to upload with your video." },
    ],
    faqs: common,
  },
  {
    slug: "tiktok-caption-generator",
    nav: "TikTok captions",
    title: "TikTok Caption Generator: Auto Captions With Word Highlights & Emojis",
    h1: "TikTok captions that stop the scroll",
    highlight: "stop the scroll",
    description:
      "Make viral-style TikTok captions automatically: bold word-by-word highlights, emojis, a hook title and a progress bar. Free, no watermark, no app.",
    intro: "The look top TikTokers use, in one click: bold captions that pop word by word, emojis on key moments and a hook title on top.",
    preset: { style: "bold-pop" },
    howTo: steps("Upload your TikTok video or paste a TikTok link."),
    tips: [
      { title: "Hook title", body: "Big text at the top for the first seconds. The proven way to stop the scroll." },
      { title: "Safe position", body: "Captions sit above TikTok's buttons and description, not behind them." },
      { title: "Tighter edit", body: "Cut “um”s and pauses automatically for a faster, punchier video." },
    ],
    faqs: common,
  },
  {
    slug: "instagram-reels-captions",
    nav: "Reels captions",
    title: "Instagram Reels Captions: Add Animated Subtitles to Reels Free",
    h1: "Animated captions for Instagram Reels",
    highlight: "Instagram Reels",
    description:
      "Add animated captions to Reels automatically. Pick from 14 styles, highlight keywords, add emojis and your logo. Free, no sign-up.",
    intro: "Reels with captions get watched longer. Upload, pick a style, add your logo and download a ready-to-post Reel.",
    preset: { style: "story" },
    howTo: steps("Upload your Reel or paste an Instagram link."),
    tips: [
      { title: "Your brand", body: "Add your logo and save your colours and font as “My style” for next time." },
      { title: "14 styles", body: "From clean Classic to bold Story and Comic. Every one is customisable." },
      { title: "Make it vertical", body: "Landscape video? Reframe it to 9:16 and your captions come along." },
    ],
    faqs: common,
  },
  {
    slug: "youtube-shorts-captions",
    nav: "Shorts captions",
    title: "YouTube Shorts Captions: Auto Subtitles for Shorts, Free",
    h1: "Captions for YouTube Shorts",
    highlight: "YouTube Shorts",
    description:
      "Auto captions for YouTube Shorts with word highlights, emojis and a progress bar. Download the MP4 or an SRT for YouTube. Free.",
    intro: "Shorts with captions keep more viewers. Generate them in a minute, style them, and export, or download the SRT for YouTube.",
    preset: { style: "karaoke" },
    howTo: steps("Upload your Short or paste a YouTube link."),
    tips: [
      { title: "Progress bar", body: "A thin bar that fills as the video plays keeps viewers to the end." },
      { title: "Karaoke style", body: "Words fill with colour as they're spoken, perfect for talking videos." },
      { title: "SRT too", body: "Upload the SRT to YouTube so your captions are also searchable." },
    ],
    faqs: common,
  },
  {
    slug: "srt-subtitle-generator",
    nav: "SRT generator",
    title: "SRT Subtitle Generator: Video to SRT File Online, Free",
    h1: "Get an SRT file from any video",
    highlight: "SRT file",
    description: "Generate SRT, VTT or TXT subtitles from video automatically in 40+ languages. Edit the text, then download. Free, no watermark, no sign-up.",
    intro: "Upload a video and get accurate subtitles with timings. Fix any word in the editor, then download SRT for YouTube, Facebook, Premiere or CapCut.",
    preset: { style: "classic" },
    howTo: steps("Upload your video or paste its link."),
    tips: [
      { title: "Every format", body: "SRT, WebVTT and plain text, in the original language, the translation, or both." },
      { title: "Accurate timing", body: "Word-level timings mean subtitles appear exactly when words are spoken." },
      { title: "Translated SRT", body: "Translate the subtitles and download a second SRT in another language." },
    ],
    faqs: common,
  },
  {
    slug: "burn-subtitles-into-video",
    nav: "Burn in subtitles",
    title: "Burn Subtitles Into Video Online: Hardcode SRT Into MP4, Free",
    h1: "Burn subtitles into your video",
    highlight: "into your video",
    description: "Hardcode an SRT or VTT into your MP4 with styled, animated subtitles. Or let AI write them. Free, no watermark, works on phone.",
    intro: "Already have an SRT? Upload the video and the subtitle file, choose a style and we burn them in, so they show on every app.",
    preset: { style: "boxed", srt: true },
    howTo: [
      "Upload your video, then open More options and import your SRT or VTT file.",
      "Press Use my subtitles. Fix any line and pick a style.",
      "Export: the subtitles are burned into the MP4, visible everywhere.",
    ],
    tips: [
      { title: "Shows everywhere", body: "Burned-in subtitles work on TikTok, Reels, WhatsApp and any player." },
      { title: "Your file, our styles", body: "Turn a plain SRT into animated, branded captions." },
      { title: "No SRT? No problem", body: "Skip the import and AI writes the subtitles for you." },
    ],
    faqs: common,
  },
  {
    slug: "translate-video-subtitles",
    nav: "Translate subtitles",
    title: "Translate Video Subtitles: Auto Translate Captions Into English & More",
    h1: "Translate your video's captions",
    highlight: "Translate",
    description:
      "Auto-translate video captions: Urdu to English, Hindi to English, English to Urdu and more. Show both languages at once. Free MP4 and SRT.",
    intro: "Reach a bigger audience without re-recording: captions in another language, or two languages at once, one under the other.",
    preset: {},
    howTo: [
      "Upload your video or paste its link, then press Generate captions.",
      "Open Boost → Translate, pick a language and choose Original, Translation or Both.",
      "Export the MP4 or download the translated SRT.",
    ],
    tips: [
      { title: "Both languages", body: "Original on top, translation below. Great for Urdu or Hindi creators growing abroad." },
      { title: "Natural wording", body: "Translations are written for captions: short, natural and true to your tone." },
      { title: "Edit translations", body: "Every translated line is editable before you export." },
    ],
    faqs: common,
  },
  {
    slug: "video-to-text-transcription",
    nav: "Video to text",
    title: "Video to Text: Free AI Transcription in Urdu, Hindi, English & 40+ Languages",
    h1: "Turn video into text",
    highlight: "text",
    description: "Transcribe video to text with AI. Copy the transcript or download TXT/SRT. Urdu, Hindi, English, Arabic and 40+ languages. Free, no sign-up.",
    intro: "Get the full transcript of any video in a minute. Copy it, download it as text, or turn it into captions.",
    preset: { style: "classic" },
    howTo: steps("Upload your video or audio, or paste a link."),
    tips: [
      { title: "Copy in one click", body: "Use Copy text to paste the transcript into a blog post, description or notes." },
      { title: "Long videos", body: "Up to an hour per video. Podcasts and lectures welcome." },
      { title: "Searchable SRT", body: "Upload the SRT to YouTube to make your video searchable." },
    ],
    faqs: common,
  },
];

export const captionPageBySlug = (slug: string) => CAPTION_PAGES.find((p) => p.slug === slug);

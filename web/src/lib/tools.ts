import type { Faq } from "./content";
import type { Aspect, Look, Mode, SmartOptions } from "./reframe";
import { SITE } from "./site";

export type ToolPreset = {
  mode?: Mode;
  aspects?: Aspect[];
  smart?: Partial<SmartOptions>;
  look?: Partial<Look>;
};

export type ToolPage = {
  slug: string;
  nav: string;            // short name for links between tool pages
  title: string;          // <title>
  h1: string;
  highlight: string;
  description: string;
  intro: string;
  preset: ToolPreset;
  howTo: string[];
  tips: { title: string; body: string }[];
  faqs: Faq[];
};

export const REFRAME_SLUG = "landscape-to-portrait-video-converter";

const common: Faq[] = [
  {
    q: "Is it free?",
    a: `Yes. ${SITE.name} Reframe is free with no sign-up and no watermark. A fair daily limit keeps the servers fast for everyone.`,
  },
  {
    q: "Which AI does it use? Is it ChatGPT?",
    a: "No chatbot is involved. Smart Reframe uses small computer-vision models that find faces, people, objects and on-screen text, plus a speech detector that knows when someone is talking. They run on our own servers; your video is never sent to an AI company.",
  },
  {
    q: "What happens to my video?",
    a: "Your upload and the finished videos are stored only so you can download them, then deleted automatically within 24 hours. They're never shared, listed publicly or used to train AI.",
  },
  {
    q: "How long can my video be?",
    a: "Up to 30 minutes per conversion and 1 GB per file. For a longer video, use Trim to pick the part you need.",
  },
  {
    q: "Can I fix a shot the AI got wrong?",
    a: "Yes. After converting, the shot editor shows every shot with the AI's choice. Drag the crop, tap the person or object to follow, or switch the layout, then apply. The video is re-rendered in seconds without analysing it again.",
  },
];

export const TOOL_PAGES: ToolPage[] = [
  {
    slug: REFRAME_SLUG,
    nav: "Landscape to portrait",
    title: "Landscape to Portrait Video Converter: AI Reframe 16:9 to 9:16 Free",
    h1: "Turn landscape video into vertical, automatically",
    highlight: "automatically",
    description:
      "Convert 16:9 landscape video to 9:16 portrait for TikTok, Reels and Shorts. AI follows the speaker, switches between people and keeps text readable. Free, no watermark.",
    intro:
      "Upload a horizontal video or paste a link. Smart Reframe follows whoever is talking, uses split screen for two people, stacks your facecam above gameplay, and never cuts off slides. Or use Blur Fill to keep everything.",
    preset: { mode: "smart" },
    howTo: [
      "Upload your landscape video (MP4, MOV, WebM, MKV) or paste a YouTube, TikTok, Instagram or Facebook link.",
      "Pick Smart Reframe (AI) or Blur Fill, and the formats you need: 9:16, 4:5 or 1:1.",
      "Convert, check the result, fix any shot in the editor, and download your vertical video.",
    ],
    tips: [
      { title: "Follows the speaker", body: "Faces are tracked and the camera cuts to whoever is talking, like a real editor. Short \"mm-hmm\"s don't cause a cut." },
      { title: "Right layout per shot", body: "Follow, Split Screen, Screen + Facecam or Fit. The AI decides shot by shot, and you can override any of them." },
      { title: "Safe for every app", body: "Faces stay clear of the like and share buttons and the caption area on TikTok, Reels and Shorts." },
    ],
    faqs: [
      { q: "How do I convert a landscape video to portrait?", a: "Upload it above, keep Smart Reframe and 9:16 selected, and press Convert. Your vertical MP4 is ready in about the length of the video." },
      { q: "What's the difference between Smart Reframe and Blur Fill?", a: "Smart Reframe crops to fill the whole vertical screen and moves the crop to follow people. Blur Fill keeps the entire original frame in the middle with a blurred copy of the video behind it, so nothing is ever cut off." },
      ...common,
    ],
  },
  {
    slug: "youtube-to-shorts-converter",
    nav: "YouTube to Shorts",
    title: "YouTube to Shorts Converter: Make Vertical Shorts From YouTube Videos",
    h1: "Turn a YouTube video into a vertical Short",
    highlight: "vertical Short",
    description:
      "Paste a YouTube link or upload a video and get a 9:16 Short with the speaker always in frame. AI reframe, trim to the best part, free and no watermark.",
    intro:
      "Paste the YouTube link of a video you own, trim it to the part you want, and Smart Reframe turns it into a vertical Short that keeps the speaker centred.",
    preset: { mode: "smart", aspects: ["9:16"], smart: { safe_zone: "shorts" } },
    howTo: [
      "Copy the link of your YouTube video (or upload the file).",
      "Use Trim to choose the moment (up to 30 minutes), keep Smart Reframe on.",
      "Convert and download the 9:16 MP4, ready to upload as a Short.",
    ],
    tips: [
      { title: "Trim first", body: "Shorts can be up to 3 minutes. Set the start and end, and only that part is converted." },
      { title: "Shorts safe zone", body: "The framing keeps faces away from the Shorts like, comment and subscribe buttons." },
      { title: "Your own content", body: "Use videos you own or have permission to repost. Re-uploading other people's work can get your channel struck." },
    ],
    faqs: [
      { q: "Does it work with YouTube links?", a: "Yes, paste a public YouTube link and we fetch the video for you. You can also upload the file you exported." },
      ...common,
    ],
  },
  {
    slug: "16-9-to-9-16-video-converter",
    nav: "16:9 to 9:16",
    title: "16:9 to 9:16 Video Converter Online: Free, AI or Blur Background",
    h1: "16:9 to 9:16 video converter",
    highlight: "9:16",
    description:
      "Convert 16:9 video to 9:16 online. Choose AI auto-crop that follows people, blurred background, centre crop or colour bars. 1080×1920 MP4, free.",
    intro: "Four ways to go from 16:9 to 9:16 in one place: AI auto-crop, blurred background, a fixed crop you position yourself, or the full video on a colour background.",
    preset: { mode: "smart", aspects: ["9:16"] },
    howTo: [
      "Upload your 16:9 video or paste a link.",
      "Choose AI Smart Reframe, Blur Fill, Crop or Fit + Colour, and preview it live.",
      "Convert to 1080×1920 MP4 and download.",
    ],
    tips: [
      { title: "1080×1920 output", body: "Full HD vertical H.264 + AAC that every app accepts. Pick 720p for faster, smaller files." },
      { title: "Also 4:5 and 1:1", body: "Tick several formats and get them all from one upload." },
      { title: "Live preview", body: "See the result in a phone frame before converting, with the app's buttons overlaid." },
    ],
    faqs: common,
  },
  {
    slug: "auto-reframe-video-ai",
    nav: "AI auto reframe",
    title: "Auto Reframe Video AI: Free Smart Crop That Follows the Speaker",
    h1: "AI auto reframe that follows the speaker",
    highlight: "follows the speaker",
    description:
      "Free AI auto reframe: tracks faces, switches to whoever is speaking, split screen for two people, facecam layout for gameplay. A free alternative to paid auto-reframe tools.",
    intro: "An AI director that watches your video shot by shot: who is on screen, who is talking, whether there's a webcam box or slides, and picks the best vertical layout for each moment.",
    preset: { mode: "smart", smart: { dynamic_zoom: true } },
    howTo: [
      "Upload the video or paste a link.",
      "Keep Smart Reframe; optionally type what to follow (a ball, a dog, a car…).",
      "Convert, review each shot in the editor, then download.",
    ],
    tips: [
      { title: "Active speaker", body: "Lip movement plus speech detection decide who is talking. The cut lands where the new speaker starts." },
      { title: "Follow anything", body: "Type an everyday object or tap it in the shot editor, and the crop follows it instead of faces." },
      { title: "Dynamic zoom", body: "Optional subtle punch-ins on emphasised moments: the edited look viewers expect." },
    ],
    faqs: common,
  },
  {
    slug: "blur-background-video",
    nav: "Blur background",
    title: "Add Blur Background to Video: Vertical Video With Blurred Sides, Free",
    h1: "Vertical video with a blurred background",
    highlight: "blurred background",
    description:
      "Fit your whole landscape video into 9:16 with a blurred background behind it. Adjust blur, dim and zoom. Free, no watermark, MP4 download.",
    intro: "Keep every pixel of your original video and fill the empty space above and below with a soft, blurred copy of it. Great for wide shots, slides and anything you don't want cropped.",
    preset: { mode: "blur" },
    howTo: ["Upload your video or paste a link.", "Adjust blur strength, dimming and zoom in the live preview.", "Convert and download the 9:16 MP4."],
    tips: [
      { title: "Nothing cut off", body: "The full frame stays visible, so text and wide shots stay intact." },
      { title: "Fine-tune the look", body: "Three blur strengths, background dimming and up to 150% foreground zoom." },
      { title: "Fast", body: "No AI analysis needed, so it converts at several times real-time speed." },
    ],
    faqs: common,
  },
  {
    slug: "resize-video-for-instagram-reels",
    nav: "Resize for Reels",
    title: "Resize Video for Instagram Reels, Stories & Feed (9:16, 4:5, 1:1)",
    h1: "Resize video for Instagram Reels and feed",
    highlight: "Reels and feed",
    description:
      "Resize any video for Instagram: 9:16 Reels and Stories, 4:5 feed and 1:1 square, all from one upload. AI keeps people in frame. Free.",
    intro: "One upload, every Instagram size. Tick 9:16 for Reels and Stories, 4:5 for the feed and 1:1 for a square post, and download each one.",
    preset: { mode: "smart", aspects: ["9:16", "4:5"], smart: { safe_zone: "reels" } },
    howTo: ["Upload your video.", "Tick 9:16, 4:5 and/or 1:1.", "Convert once and download every format."],
    tips: [
      { title: "Reels safe zone", body: "Faces stay clear of the Reels buttons and caption area." },
      { title: "Analysed once", body: "The AI watches the video once and renders every format from it." },
      { title: "Feed-ready 4:5", body: "4:5 takes up the most space in the Instagram feed." },
    ],
    faqs: common,
  },
  {
    slug: "podcast-to-shorts",
    nav: "Podcast to Shorts",
    title: "Podcast to Shorts & Reels: AI Speaker Switching and Split Screen",
    h1: "Turn podcast clips into vertical Shorts",
    highlight: "vertical Shorts",
    description:
      "Make vertical clips from video podcasts and interviews. The AI cuts to whoever is speaking or shows both people in split screen. Free, no watermark.",
    intro: "Two people at a table, a wide shot and close-ups? Smart Reframe follows the active speaker, switches when the other person talks, and uses split screen for fast back-and-forth.",
    preset: { mode: "smart", smart: { two_person: "auto" } },
    howTo: ["Upload the episode or paste its link.", "Trim to the clip you want (up to 30 minutes).", "Convert, then fix any shot in the editor and download."],
    tips: [
      { title: "Speaker switching", body: "Cuts follow the conversation and ignore short interruptions." },
      { title: "Split screen", body: "Rapid back-and-forth? Both people are shown, one above the other." },
      { title: "Wide shots handled", body: "Group shots too wide to crop are shown whole over a blurred background." },
    ],
    faqs: common,
  },
  {
    slug: "gameplay-to-tiktok",
    nav: "Gameplay to TikTok",
    title: "Gameplay to TikTok: Facecam + Game Vertical Layout, Automatic",
    h1: "Gameplay with facecam to vertical, automatically",
    highlight: "automatically",
    description:
      "Turn streams and gameplay with a webcam overlay into vertical TikToks and Shorts: facecam on top, game below, detected automatically. Free.",
    intro: "Smart Reframe spots your webcam box over the game or screen recording and stacks it above the action, the layout streamers use on TikTok and Shorts.",
    preset: { mode: "smart", smart: { facecam: true } },
    howTo: ["Upload your clip or paste a Twitch / YouTube link.", "Keep Smart Reframe on: the facecam is found for you.", "Convert and download the vertical clip."],
    tips: [
      { title: "Facecam detected", body: "No box to draw: the webcam is found from your face and the frame around it." },
      { title: "Tutorials too", body: "Works for screen recordings and coding streams with a webcam in the corner." },
      { title: "Switch any shot", body: "Prefer just the game for a shot? Change that shot's layout in the editor." },
    ],
    faqs: common,
  },
];

export const toolBySlug = (slug: string) => TOOL_PAGES.find((t) => t.slug === slug);

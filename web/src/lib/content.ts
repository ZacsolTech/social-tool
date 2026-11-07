import type { PlatformId } from "./platforms";
import { SITE } from "./site";

export type Faq = { q: string; a: string };

export type PlatformContent = {
  title: string;        // <title>
  h1: string;
  highlight: string;    // word(s) in the h1 shown in the accent serif
  description: string;  // meta description
  intro: string;
  howTo: string[];      // 3 steps
  tips: { title: string; body: string }[];
  faqs: Faq[];
};

const common = (name: string): Faq[] => [
  {
    q: `Is the ${name} downloader free?`,
    a: "Yes. Every download is free with no sign-up and no daily limit for normal use. We never show pop-ups or redirect you to other sites.",
  },
  {
    q: "Do you keep a copy of my videos?",
    a: "No. Downloads stream straight from the platform to your device and are never saved on our servers. We don't build galleries or index anything you download.",
  },
  {
    q: "Can I download private posts?",
    a: `No. ${SITE.name} only works with public posts. Only download content you own or have permission to use.`,
  },
];

export const CONTENT: Record<PlatformId, PlatformContent> = {
  youtube: {
    title: "YouTube Video Downloader - Download YouTube Videos & Shorts in HD (MP4, MP3)",
    h1: "YouTube video downloader, up to 4K",
    highlight: "up to 4K",
    description:
      "Download YouTube videos and Shorts in 1080p, 2K or 4K as MP4, or convert YouTube to MP3. Paste a link, pick a quality, done. Free, no sign-up, no pop-ups.",
    intro:
      "Save YouTube videos and Shorts as MP4 in every quality YouTube offers, from 144p up to 4K, or turn them into MP3. Video and sound are merged for you into one file that plays everywhere.",
    howTo: [
      "On YouTube, tap Share → Copy link (works for videos, Shorts and youtu.be links).",
      "Paste the link above. We list every available quality.",
      "Pick 1080p, 4K or MP3. We merge video and audio on the fly and it downloads in your browser.",
    ],
    tips: [
      { title: "Up to 4K", body: "YouTube keeps HD video and sound in separate streams. We merge them into one MP4 with sound, up to 2160p." },
      { title: "YouTube to MP3", body: "Save talks, podcasts and music you have rights to as 192 kbps MP3 or original-quality M4A." },
      { title: "Shorts supported", body: "youtube.com/shorts links work the same way, ready to re-edit for Reels or TikTok." },
    ],
    faqs: [
      { q: "Can I download YouTube videos in 4K?", a: "Yes, when the video was uploaded in 4K. Pick 4K in the list. Very large files (over 1 GB) are hidden to keep downloads reliable; choose 1080p instead." },
      { q: "How do I convert YouTube to MP3?", a: "Paste the link and choose MP3. The audio is converted to a 192 kbps MP3. M4A keeps YouTube's original audio quality." },
      { q: "Does it work with YouTube Shorts?", a: "Yes. Paste any youtube.com/shorts link." },
      { q: "Can I download a whole playlist?", a: "Not yet. If the link is part of a playlist, we download just that video." },
      { q: "Can I download private, members-only or age-restricted videos?", a: "No. Only public videos are supported." },
      ...common("YouTube"),
    ],
  },
  tiktok: {
    title: "TikTok Downloader - Save TikTok Videos Without Watermark (HD MP4 & MP3)",
    h1: "TikTok video downloader without watermark",
    highlight: "without watermark",
    description:
      "Download TikTok videos without watermark in HD. Paste a TikTok link and save it as MP4 or MP3 in seconds. Free, no sign-up, no pop-ups.",
    intro:
      "Save any public TikTok as a clean HD MP4 with no watermark, or pull out just the sound as MP3. It works with full links and the short vm.tiktok.com links from the share button.",
    howTo: [
      "In TikTok, tap Share → Copy link on the video you want.",
      "Paste the link above. We detect it as TikTok right away.",
      "Pick HD MP4 (no watermark) or MP3 and your download starts.",
    ],
    tips: [
      { title: "No watermark by default", body: "We always choose the original upload over the watermarked copy when TikTok provides one." },
      { title: "Sounds as MP3", body: "Save trending sounds and voice-overs as 192 kbps MP3 for your own edits." },
      { title: "Short links work", body: "vm.tiktok.com and vt.tiktok.com share links are expanded automatically." },
    ],
    faqs: [
      { q: "How do I download a TikTok without the watermark?", a: "Paste the TikTok link and choose the top MP4 option. We fetch the original file, which does not have the moving TikTok logo." },
      { q: "Can I save a TikTok sound as MP3?", a: "Yes. After pasting the link, choose MP3. The audio is converted to a 192 kbps MP3 that plays everywhere." },
      ...common("TikTok"),
    ],
  },
  instagram: {
    title: "Instagram Reels Downloader - Download Reels, Videos & Carousels in HD",
    h1: "Instagram Reels downloader in full HD",
    highlight: "full HD",
    description:
      "Download Instagram Reels, videos and carousel posts in HD. Paste the link, pick a quality, save as MP4 or MP3. Free, no login, no pop-ups.",
    intro:
      "Save public Instagram Reels and video posts in their original quality. Carousel posts with several videos show every clip, so you can download one or all of them.",
    howTo: [
      "Open the Reel or post, tap ⋯ or the paper plane, then Copy link.",
      "Paste the link above. Carousels list every video.",
      "Choose a quality or MP3 and save it to your phone or computer.",
    ],
    tips: [
      { title: "Carousels supported", body: "Posts with several videos show each one with its own download buttons, plus Download all." },
      { title: "Original quality", body: "We list every quality Instagram offers and pick the one that plays everywhere as Best." },
      { title: "No login needed", body: "We never ask for your Instagram password. Public posts only." },
    ],
    faqs: [
      { q: "Can I download Instagram Stories?", a: "Stories usually need a login, so they aren't supported. Public Reels, videos and carousel posts work." },
      { q: "Why does my Reel say it's private?", a: "The account is private or the post needs a login. We can only download public posts." },
      ...common("Instagram"),
    ],
  },
  facebook: {
    title: "Facebook Video Downloader - Save Facebook Videos & Reels in HD",
    h1: "Facebook video downloader in HD",
    highlight: "in HD",
    description:
      "Download Facebook videos and Reels in HD or SD. Paste a Facebook or fb.watch link and save as MP4 or MP3. Free, fast, no sign-up.",
    intro:
      "Download public Facebook videos, Watch videos and Reels in HD. Works with facebook.com, fb.watch and m.facebook.com links.",
    howTo: [
      "On the video, tap Share → Copy link.",
      "Paste the link above.",
      "Choose HD, SD or MP3 and save it.",
    ],
    tips: [
      { title: "HD and SD", body: "Facebook offers HD and SD files. HD is picked by default; SD is smaller for slow connections." },
      { title: "fb.watch links", body: "Short fb.watch links from the share sheet work directly." },
      { title: "Audio only", body: "Turn a talk or live replay into an MP3 for listening on the go." },
    ],
    faqs: [
      { q: "Can I download videos from private groups?", a: "No. Videos in private groups or with restricted audiences need a login, so they can't be downloaded." },
      ...common("Facebook"),
    ],
  },
  x: {
    title: "Twitter (X) Video Downloader - Download X Videos & GIFs in HD",
    h1: "X / Twitter video downloader",
    highlight: "video downloader",
    description:
      "Download videos and GIFs from X (Twitter) in the best quality. Paste a post link and save MP4 or MP3. Free, no login, no pop-ups.",
    intro:
      "Save videos and GIFs from public X (Twitter) posts. If a post has several videos, each one gets its own download buttons.",
    howTo: [
      "On the post, tap Share → Copy link.",
      "Paste the link above (x.com and twitter.com both work).",
      "Choose a quality and download.",
    ],
    tips: [
      { title: "Every quality", body: "X stores several sizes. We list them all so you can choose quality or a smaller file." },
      { title: "GIFs as MP4", body: "X GIFs are really videos, so they download as MP4 that you can share anywhere." },
      { title: "Multi-video posts", body: "Posts with up to four videos list each one separately." },
    ],
    faqs: [
      { q: "Does it work with twitter.com links?", a: "Yes. Both x.com and twitter.com links work." },
      ...common("X"),
    ],
  },
  reddit: {
    title: "Reddit Video Downloader - Download Reddit Videos With Sound",
    h1: "Reddit video downloader with sound",
    highlight: "with sound",
    description:
      "Download Reddit videos with audio in HD. Reddit stores sound separately; we merge it for you into one MP4. Free and fast.",
    intro:
      "Reddit keeps video and sound in separate files, which is why many downloaders give you a silent clip. We merge them into one MP4 with sound.",
    howTo: [
      "On the post, tap Share → Copy link.",
      "Paste the link above.",
      "Pick a quality. We join video and audio automatically.",
    ],
    tips: [
      { title: "Sound included", body: "Video and audio are merged on our server, so the file just works." },
      { title: "v.redd.it links", body: "Direct v.redd.it links and normal post links both work." },
      { title: "MP3 too", body: "Save just the audio from any Reddit video." },
    ],
    faqs: [
      { q: "Why do other Reddit downloads have no sound?", a: "Reddit serves audio as a separate file. We download both and merge them into a single MP4." },
      ...common("Reddit"),
    ],
  },
  pinterest: {
    title: "Pinterest Video Downloader - Save Pinterest Videos in HD",
    h1: "Pinterest video downloader in HD",
    highlight: "in HD",
    description:
      "Download Pinterest video pins in up to 1080p. Paste a pin or pin.it link and save as MP4, MP3 or cover image. Free and no sign-up.",
    intro:
      "Save Pinterest video pins in up to 1080p, or grab the cover image. Works with pinterest.com links in every country domain and pin.it short links.",
    howTo: [
      "On the pin, tap Share → Copy link.",
      "Paste the link above.",
      "Choose a quality, MP3 or the cover image.",
    ],
    tips: [
      { title: "Up to 1080p", body: "We list every resolution Pinterest stores, from 240p up to 1080p." },
      { title: "Cover images", body: "Download the pin's cover image in full size with one tap." },
      { title: "All country sites", body: "pinterest.co.uk, pinterest.de and other domains work too." },
    ],
    faqs: [
      { q: "Can I download image pins?", a: "You can save the cover image of video pins. Pure image pins are coming in a later update." },
      ...common("Pinterest"),
    ],
  },
  dailymotion: {
    title: "Dailymotion Video Downloader - Download Dailymotion Videos in HD",
    h1: "Dailymotion video downloader",
    highlight: "downloader",
    description:
      "Download Dailymotion videos in HD as MP4 or MP3. Paste the link and save it in seconds. Free, no sign-up, no pop-ups.",
    intro: "Save public Dailymotion videos in the quality you choose, or extract the audio as MP3.",
    howTo: ["Copy the Dailymotion video link.", "Paste it above.", "Choose a quality and download."],
    tips: [
      { title: "Multiple qualities", body: "Pick from every resolution Dailymotion offers." },
      { title: "dai.ly links", body: "Short dai.ly links are supported." },
      { title: "Audio only", body: "Extract an MP3 from any public video." },
    ],
    faqs: common("Dailymotion"),
  },
  twitch: {
    title: "Twitch Clip Downloader - Download Twitch Clips in HD",
    h1: "Twitch clip downloader",
    highlight: "clip downloader",
    description:
      "Download Twitch clips in HD as MP4. Paste a clip link and save it in seconds. Free, no sign-up, no pop-ups.",
    intro: "Save your own Twitch clips to repost as Shorts, Reels or TikToks. Clips and short VODs are supported.",
    howTo: ["Open the clip and copy its link.", "Paste it above.", "Choose a quality and download."],
    tips: [
      { title: "Made for repurposing", body: "Clips download as MP4 ready for editing. 9:16 resize is coming soon." },
      { title: "HD quality", body: "Get the clip in the best quality Twitch stores." },
      { title: "Fast", body: "Clips are short, so most are ready in a few seconds." },
    ],
    faqs: common("Twitch"),
  },
};

export const HOME_FAQS: Faq[] = [
  {
    q: `Which sites does ${SITE.name} support?`,
    a: "YouTube (videos and Shorts), TikTok, Instagram, Facebook, X (Twitter), Reddit, Pinterest, Dailymotion and Twitch. Paste any public post link and we detect the platform automatically.",
  },
  {
    q: "Is it really free with no watermark?",
    a: "Yes. Downloads are free, need no account, and we never add our own watermark. For TikTok we pick the original file without the TikTok watermark whenever it is available.",
  },
  {
    q: "How do I use it on my phone?",
    a: `Open ${SITE.name} in your browser and tap Install (or Add to Home Screen). Then, in TikTok or Instagram, tap Share and pick ${SITE.name}. The link opens here and starts automatically.`,
  },
  {
    q: "Can I get just the audio?",
    a: "Yes. Every video can be saved as a 192 kbps MP3, and M4A in original quality when the platform provides it.",
  },
  {
    q: "Do you store my videos or links?",
    a: "No. Downloads stream straight to your device and are never saved on our servers. Your recent links are kept only in your own browser, and you can clear them anytime.",
  },
  {
    q: "Is downloading videos legal?",
    a: "Downloading for personal use, or downloading content you own or have permission to use, is generally fine. Re-uploading someone else's work without permission is not. Please respect creators' rights.",
  },
];

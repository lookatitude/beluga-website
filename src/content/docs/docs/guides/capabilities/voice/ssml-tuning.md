---
title: SSML Tuning for Expressive Speech
description: "Control TTS pauses, emphasis, and prosody with SSML in Go — build SSML safely, add it automatically from text cues, and feed it to Beluga AI TTS engines."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, SSML, TTS, expressive speech, pause control, speech emphasis, prosody, text-to-speech"
---

Speech Synthesis Markup Language (SSML) provides granular control over text-to-speech output, enabling pauses, emphasis, pitch adjustment, and pronunciation overrides. Without it, TTS engines apply default prosody that may not match the conversational context: a notification should sound different from a thoughtful explanation, and a brand name needs consistent pronunciation. This guide shows how to build SSML safely in Go, derive it automatically from cues in agent output, and pass it to Beluga's TTS engines.

## What You Will Build

An expressive TTS setup that:

- constructs SSML with a small builder that escapes text correctly,
- adds emphasis and pauses automatically from text cues (quotes, ALL CAPS, `**bold**`, punctuation),
- falls back to plain text when a provider rejects markup, and
- plugs into a Beluga voice pipeline as a `voice.FrameProcessor` in front of TTS.

## Prerequisites

- An API key for one of Beluga's TTS providers (`elevenlabs`, `cartesia`, `fish`, `groq`, `lmnt`, `playht`, `smallest`)
- Basic familiarity with XML syntax

## How Beluga Handles SSML

Beluga's `tts.TTS` interface takes a plain `string`:

```go
Synthesize(ctx context.Context, text string, opts ...tts.Option) ([]byte, error)
```

Beluga does not parse, validate, or strip SSML. The providers forward the string to the upstream API unchanged, so whether the tags change the audio depends on what that provider's API accepts. Check your provider's documentation. Some APIs interpret only a subset (often just `<break>`), and some read tags out loud as text. Beluga does not ship Google Cloud or Azure TTS providers, the two APIs with the broadest SSML support. To use them, implement `tts.TTS` yourself and register it with `tts.Register`.

For provider-independent control over speaking rate, use `tts.WithSpeed`. The `lmnt`, `playht`, `smallest`, and `groq` providers send it to their APIs.

## What is SSML?

SSML is an XML-based markup language that wraps plain text with directives for the speech synthesizer. Instead of passing raw text and relying on the TTS engine to infer appropriate delivery, you pass structured XML that explicitly controls timing, emphasis, and pronunciation.

```xml
<speak>
  Hello! <break time="500ms"/>
  I am very <emphasis level="strong">excited</emphasis> to meet you.
</speak>
```

## Step 1: Synthesize Marked-Up Text

Create a TTS engine from the registry and pass the SSML string to `Synthesize`:

```go
package main

import (
	"context"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/tts"
	_ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

const greeting = `<speak>
  Hello! <break time="500ms"/>
  I am very <emphasis level="strong">excited</emphasis> to meet you.
  <break time="300ms"/>
  How can I help you today?
</speak>`

func main() {
	ctx := context.Background()

	engine, err := tts.New("elevenlabs", tts.Config{
		Voice: "rachel",
		Extra: map[string]any{"api_key": os.Getenv("ELEVENLABS_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create TTS engine: %v", err)
	}

	// The string is forwarded to the provider unchanged.
	audio, err := engine.Synthesize(ctx, greeting)
	if err != nil {
		log.Fatalf("synthesize: %v", err)
	}

	if err := os.WriteFile("greeting.mp3", audio, 0o644); err != nil {
		log.Fatalf("write file: %v", err)
	}
}
```

## Step 2: Common SSML Tags

Each SSML tag addresses a specific aspect of speech delivery. Provider support varies tag by tag.

### Break (Pauses)

Breaks create silence between phrases. Use them to separate logical sections, give the listener time to process information, or create a conversational rhythm. The `time` attribute provides exact control, while `strength` uses the engine's natural pause model.

```xml
<break time="500ms"/>      <!-- Pause for 500 milliseconds -->
<break time="1s"/>         <!-- Pause for 1 second -->
<break strength="strong"/> <!-- Natural paragraph-level pause -->
```

### Emphasis

Emphasis changes the volume, pitch, and speed of a word to draw attention to it. This is useful for highlighting key terms, correcting misunderstandings, or expressing urgency.

```xml
<emphasis level="strong">important</emphasis>  <!-- Louder, slower -->
<emphasis level="moderate">notable</emphasis>   <!-- Slightly stressed -->
<emphasis level="reduced">minor</emphasis>      <!-- Softer, faster -->
```

### Prosody (Pitch, Rate, Volume)

Prosody controls the overall delivery style of a phrase. Adjusting rate and pitch together can convey emotions: slow rate with low pitch suggests seriousness, while fast rate with higher pitch suggests excitement.

```xml
<prosody rate="slow" pitch="+2st">
  I'm speaking slowly and at a higher pitch.
</prosody>
<prosody volume="loud" rate="fast">
  This is urgent!
</prosody>
```

### Say-As (Interpretation)

Say-as tells the engine how to interpret ambiguous content. Without it, "12/25/2025" might be read as a fraction. The `interpret-as` attribute disambiguates the intended reading.

```xml
<say-as interpret-as="telephone">555-0199</say-as>
<say-as interpret-as="date" format="mdy">12/25/2025</say-as>
<say-as interpret-as="cardinal">42</say-as>
```

### Phoneme (Pronunciation Override)

Phoneme overrides the default pronunciation for words the engine mispronounces. This is useful for brand names, technical terms, and proper nouns.

```xml
<phoneme alphabet="ipa" ph="p&#618;&#712;k&#593;&#720;n">pecan</phoneme>
```

## Step 3: Programmatic SSML Builder

Manual XML string construction is error-prone: unclosed tags, unescaped `&` or `<` in user text, and malformed attributes cause synthesis failures at runtime. A builder escapes text and keeps the structure valid:

```go
package ssml

import (
	"fmt"
	"html"
	"strings"
)

// Builder constructs SSML documents programmatically.
type Builder struct {
	parts []string
}

// NewBuilder returns a new SSML builder.
func NewBuilder() *Builder {
	return &Builder{}
}

// Text adds plain text content, escaping XML special characters.
func (b *Builder) Text(text string) *Builder {
	b.parts = append(b.parts, html.EscapeString(text))
	return b
}

// Pause adds a break with the given duration (e.g., "500ms", "1s").
func (b *Builder) Pause(duration string) *Builder {
	b.parts = append(b.parts, fmt.Sprintf(`<break time="%s"/>`, html.EscapeString(duration)))
	return b
}

// Emphasis wraps text with the given emphasis level (strong, moderate, reduced).
func (b *Builder) Emphasis(text, level string) *Builder {
	b.parts = append(b.parts, fmt.Sprintf(`<emphasis level="%s">%s</emphasis>`,
		html.EscapeString(level), html.EscapeString(text)))
	return b
}

// Prosody wraps text with rate and pitch adjustments.
func (b *Builder) Prosody(text, rate, pitch string) *Builder {
	b.parts = append(b.parts, fmt.Sprintf(`<prosody rate="%s" pitch="%s">%s</prosody>`,
		html.EscapeString(rate), html.EscapeString(pitch), html.EscapeString(text)))
	return b
}

// Build returns the complete SSML document.
func (b *Builder) Build() string {
	return "<speak>" + strings.Join(b.parts, "") + "</speak>"
}
```

Usage, with `engine` from Step 1:

```go
	speech := ssml.NewBuilder().
		Text("Welcome to Beluga AI.").
		Pause("500ms").
		Text("Let me help you with ").
		Emphasis("deployment", "strong").
		Text(" today.").
		Build()

	audio, err := engine.Synthesize(ctx, speech)
	if err != nil {
		log.Fatalf("synthesize: %v", err)
	}
```

## Step 4: Add Emphasis and Pauses Automatically

Agents produce plain text, so you usually want prosody derived from cues already in that text rather than asking the LLM to emit XML. The processor below maps quoted text and `**bold**` to moderate emphasis, ALL-CAPS words to strong emphasis, and punctuation to pauses. It escapes the input first, so user text can never inject tags.

```go
package main

import (
	"fmt"
	"html"
	"regexp"
	"strings"
	"time"
)

// SSMLProcessor turns plain text into SSML using text cues.
type SSMLProcessor struct {
	AddEmphasis bool
	AddPauses   bool
	// Pauses maps a punctuation mark to the break inserted after it.
	Pauses map[string]time.Duration
}

// NewSSMLProcessor returns a processor with conservative pause defaults.
func NewSSMLProcessor() *SSMLProcessor {
	return &SSMLProcessor{
		AddEmphasis: true,
		AddPauses:   true,
		Pauses: map[string]time.Duration{
			".": 500 * time.Millisecond,
			"!": 500 * time.Millisecond,
			"?": 500 * time.Millisecond,
			";": 300 * time.Millisecond,
			":": 300 * time.Millisecond,
			",": 250 * time.Millisecond,
		},
	}
}

var emphasisPatterns = []struct {
	re    *regexp.Regexp
	level string
}{
	{regexp.MustCompile(`\*\*([^*]+)\*\*`), "moderate"},
	{regexp.MustCompile(`&#34;([^&]+)&#34;`), "moderate"}, // quotes, after escaping
	{regexp.MustCompile(`\b([A-Z]{2,})\b`), "strong"},
}

// Process returns an SSML document for text.
func (p *SSMLProcessor) Process(text string) string {
	// Escape rune by rune, inserting breaks after punctuation in the raw text.
	// Working on the raw runes keeps breaks out of entities such as &#34;.
	var b strings.Builder
	for _, r := range text {
		b.WriteString(html.EscapeString(string(r)))
		if d, ok := p.Pauses[string(r)]; ok && p.AddPauses {
			fmt.Fprintf(&b, `<break time="%dms"/>`, d.Milliseconds())
		}
	}
	out := b.String()

	if p.AddEmphasis {
		for _, pat := range emphasisPatterns {
			out = pat.re.ReplaceAllString(out, `<emphasis level="`+pat.level+`">$1</emphasis>`)
		}
	}

	return "<speak>" + out + "</speak>"
}

// Prosody wraps already-escaped SSML content with rate, pitch, and volume controls.
func Prosody(content, rate, pitch, volume string) string {
	var attrs []string
	if rate != "" {
		attrs = append(attrs, fmt.Sprintf(`rate="%s"`, html.EscapeString(rate)))
	}
	if pitch != "" {
		attrs = append(attrs, fmt.Sprintf(`pitch="%s"`, html.EscapeString(pitch)))
	}
	if volume != "" {
		attrs = append(attrs, fmt.Sprintf(`volume="%s"`, html.EscapeString(volume)))
	}
	if len(attrs) == 0 {
		return content
	}
	return fmt.Sprintf(`<prosody %s>%s</prosody>`, strings.Join(attrs, " "), content)
}

func main() {
	p := NewSSMLProcessor()
	fmt.Println(p.Process(`Hello! This is IMPORTANT. Say "yes" if you agree, or **no** if not.`))
}
```

How it works:

1. **Escaping first.** `html.EscapeString` turns `<`, `>`, `&`, `'`, and `"` into entities, so any markup that reaches the engine comes from the processor, not from the input. Double quotes become `&#34;`, which is why the quote pattern matches the escaped form.
2. **Pauses before emphasis.** Breaks are inserted in the same pass that escapes the raw text, before any emphasis tags exist, so a break never lands inside an entity or a tag attribute. Sentence-ending punctuation gets 500 ms, commas 250 ms. Tune the map per voice and speaking rate. Note that a decimal point (`3.5`) also gets a pause; skip `.` between digits if that matters for your content.
3. **Emphasis from existing conventions.** Quoted text and `**bold**` get moderate emphasis; ALL-CAPS words get strong emphasis. Use ALL CAPS sparingly, or every sentence will sound urgent.

**Key insight:** too much SSML sounds robotic, too little sounds monotone. Over-tagging with emphasis dilutes real importance, and over-pausing creates awkward silences. Start with the conservative defaults and tune from listening tests.

## Step 5: Fall Back When a Provider Rejects Markup

If a provider returns an error for SSML input, retry with the tags stripped. This lets you write SSML throughout your application and degrade gracefully:

```go
package speech

import (
	"context"
	"html"
	"regexp"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/voice/tts"
)

var tagPattern = regexp.MustCompile(`<[^>]+>`)

// SafeSynthesize synthesizes input and retries with SSML tags stripped if the
// provider rejects the marked-up version.
func SafeSynthesize(ctx context.Context, engine tts.TTS, input string, opts ...tts.Option) ([]byte, error) {
	if !isSSML(input) {
		return engine.Synthesize(ctx, input, opts...)
	}
	audio, err := engine.Synthesize(ctx, input, opts...)
	if err == nil {
		return audio, nil
	}
	return engine.Synthesize(ctx, stripTags(input), opts...)
}

func isSSML(input string) bool {
	return strings.HasPrefix(strings.TrimSpace(input), "<speak>")
}

func stripTags(input string) string {
	plain := tagPattern.ReplaceAllString(input, " ")
	return strings.Join(strings.Fields(html.UnescapeString(plain)), " ")
}
```

This only helps when the provider returns an error. A provider that accepts the request but reads the tags aloud cannot be detected from the response. For those, strip tags up front with `stripTags`.

## Step 6: Apply SSML Inside a Voice Pipeline

In a cascading pipeline, text frames flow from the LLM stage to TTS. Insert a `voice.FrameLoop` stage that rewrites each text frame into SSML before `tts.AsFrameProcessor` synthesizes it. This uses `SSMLProcessor` from Step 4:

```go
import (
	"context"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/tts"
)

// ssmlStage converts text frames to SSML and passes other frames through.
func ssmlStage(p *SSMLProcessor) voice.FrameProcessor {
	return voice.FrameLoop(func(ctx context.Context, f voice.Frame) ([]voice.Frame, error) {
		if f.Type != voice.FrameText {
			return []voice.Frame{f}, nil
		}
		return []voice.Frame{voice.NewTextFrame(p.Process(f.Text()))}, nil
	})
}

// expressiveTTS chains SSML generation in front of a TTS engine. Pass the
// result to voice.WithTTS when building the pipeline.
func expressiveTTS(engine tts.TTS, sampleRate int) voice.FrameProcessor {
	return voice.Chain(
		ssmlStage(NewSSMLProcessor()),
		tts.AsFrameProcessor(engine, sampleRate),
	)
}
```

`voice.WithTTS` accepts any `voice.FrameProcessor`, so `voice.NewPipeline(..., voice.WithTTS(expressiveTTS(engine, 24000)))` is all the wiring you need.

## Verification

1. Generate speech with `<break time="3s"/>` and check for three seconds of silence in the output. If you hear "break time" read aloud, your provider does not interpret SSML; strip tags for that provider.
2. Use `<emphasis level="strong">` on a word and listen for the volume and pitch change.
3. Compare the same text rendered with and without SSML.
4. Run `SSMLProcessor.Process` on input containing `<`, `&`, and quotes and confirm the output is well-formed XML.
5. Test the `SafeSynthesize` fallback with a provider that rejects SSML.

## Next Steps

- [Cloning Voices with ElevenLabs](/docs/guides/capabilities/voice/elevenlabs-cloning) -- High-fidelity voice synthesis
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Integrate expressive TTS into voice agents
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Balance detection thresholds for natural conversation

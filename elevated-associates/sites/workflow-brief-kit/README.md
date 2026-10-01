# Workflow Brief Kit store

Static site: a sales page (`index.html`) and the buyer delivery page (`k-Et4kkMr9t7ISFMB5/`), which renders the full kit with Download as Word and Print / Save as PDF. No build step.

## Go live (Nicole, one time)

1. Vercel → Add New → Project → import `nicolelung20-cmyk/supergrok`, set **Root Directory** to `elevated-associates/sites/workflow-brief-kit`, Framework "Other", then Deploy. (Netlify works the same way with this folder as the base directory.)
2. Stripe → Payment Links → the $47 Workflow Brief Kit link → After payment → "Don't show confirmation page", redirect to `https://<your-site>/k-Et4kkMr9t7ISFMB5/`.
3. Google Search Console: add the site and submit `https://<your-site>/` so it can be found.

The delivery path is unguessable and blocked from search engines (robots.txt and an X-Robots-Tag header), but anyone with the link can open it. To rotate it, rename the folder and update the Stripe redirect.

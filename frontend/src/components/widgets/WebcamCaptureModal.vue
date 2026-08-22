<template>
  <BaseModal
    :modelValue="modelValue"
    title="Prendre une photo"
    maxWidth="620px"
    :closeOnOutside="false"
    @update:modelValue="close"
  >
    <div class="capture-body">
      <div v-if="error" class="capture-error">{{ error }}</div>

      <!-- Scène : la vidéo est recadrée en CSS au ratio de la photo attendue, exactement comme le
           canvas la recadrera à la capture (voir computeCropRect) — ce que l'utilisateur voit dans
           le cadre est donc ce qu'il obtiendra, au pixel près. -->
      <div v-show="!error && !preview" class="capture-stage" :style="{ aspectRatio: String(ratio) }">
        <video ref="videoRef" class="capture-video" autoplay playsinline muted></video>

        <!-- Gabarit : ellipse de placement du visage + repères de hauteur. En SVG plutôt qu'en
             bordures CSS pour que l'extérieur du visage soit assombri d'un seul masque, sans
             empiler quatre div de voile. `pointer-events: none` : purement indicatif. -->
        <svg class="capture-guide" viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <mask id="face-hole">
              <rect x="0" y="0" width="100" height="100" fill="white" />
              <ellipse
                :cx="guide.centerX * 100" :cy="guide.centerY * 100"
                :rx="guide.radiusX * 100" :ry="guide.radiusY * 100"
                fill="black"
              />
            </mask>
          </defs>
          <rect x="0" y="0" width="100" height="100" fill="rgba(0,0,0,0.35)" mask="url(#face-hole)" />
          <ellipse
            :cx="guide.centerX * 100" :cy="guide.centerY * 100"
            :rx="guide.radiusX * 100" :ry="guide.radiusY * 100"
            fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="0.6" stroke-dasharray="2 1.5"
            vector-effect="non-scaling-stroke"
          />
          <!-- Repères du sommet du crâne et du menton : c'est la hauteur du visage (32 à 36 mm sur
               45) qui fait accepter ou refuser une photo d'identité, pas seulement son centrage. -->
          <line
            :x1="(guide.centerX - guide.radiusX - 0.06) * 100" :y1="(guide.centerY - guide.radiusY) * 100"
            :x2="(guide.centerX - guide.radiusX - 0.01) * 100" :y2="(guide.centerY - guide.radiusY) * 100"
            stroke="rgba(255,255,255,0.9)" stroke-width="0.6" vector-effect="non-scaling-stroke"
          />
          <line
            :x1="(guide.centerX - guide.radiusX - 0.06) * 100" :y1="(guide.centerY + guide.radiusY) * 100"
            :x2="(guide.centerX - guide.radiusX - 0.01) * 100" :y2="(guide.centerY + guide.radiusY) * 100"
            stroke="rgba(255,255,255,0.9)" stroke-width="0.6" vector-effect="non-scaling-stroke"
          />
        </svg>

        <div class="capture-hint">Placez votre visage dans l'ovale, regard vers l'objectif.</div>
      </div>

      <!-- Contrôle avant validation : une photo d'identité ratée se voit tout de suite, et se
           reprend en un clic — plutôt que d'être découverte plus tard dans la fiche. -->
      <div v-if="preview" class="capture-stage" :style="{ aspectRatio: String(ratio) }">
        <img :src="preview" class="capture-preview" alt="Photo capturée" />
      </div>
    </div>

    <template #footer>
      <template v-if="preview">
        <BaseButton variant="secondary" @click="retake">Reprendre</BaseButton>
        <BaseButton variant="primary" @click="confirm">Utiliser cette photo</BaseButton>
      </template>
      <template v-else>
        <BaseButton variant="secondary" @click="close">Annuler</BaseButton>
        <!-- Aucun bouton de capture quand la webcam est hors de portée (absente, refusée, ou
             connexion non sécurisée) : il ne resterait qu'à cliquer sur un bouton qui ne peut rien
             faire. La seule issue est de fermer et de passer par « Parcourir… », le message
             d'erreur le dit — autant ne proposer que cette issue. -->
        <BaseButton v-if="!error" variant="primary" :disabled="!streaming" @click="capture">
          Prendre la photo
        </BaseButton>
      </template>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
// Capture d'une photo d'identité par la webcam, pour un champ binaire à widget="image" (voir
// ImageField.vue). La photo est découpée au format 35×45 mm avant d'être remise au champ : ce n'est
// pas une capture brute qu'on rognera plus tard, c'est déjà une photo d'identité.
//
// ⚠️ `getUserMedia` n'existe que dans un contexte sécurisé (https, ou localhost en développement) :
// sur une instance servie en http clair, le navigateur ne l'expose tout simplement pas. Le message
// d'erreur le dit explicitement plutôt que de laisser un bouton sans effet.
import { onBeforeUnmount, ref, watch } from 'vue';
import BaseModal from '../BaseModal.vue';
import BaseButton from '../BaseButton.vue';
import type { BinaryValue } from './BinaryFileField.vue';
import { FACE_GUIDE, ID_PHOTO_OUTPUT_WIDTH, ID_PHOTO_RATIO, computeCropRect } from './photoCrop';

const props = withDefaults(defineProps<{
  modelValue: boolean;
  /** Largeur/hauteur de la photo produite — paramétrable par widgetParams (voir ImageField.vue). */
  ratio?: number;
  outputWidth?: number;
}>(), {
  ratio: ID_PHOTO_RATIO,
  outputWidth: ID_PHOTO_OUTPUT_WIDTH,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'capture', value: BinaryValue): void;
}>();

const videoRef = ref<HTMLVideoElement | null>(null);
const preview = ref<string | null>(null);
const error = ref('');
const streaming = ref(false);
const guide = FACE_GUIDE;

let stream: MediaStream | null = null;

async function start() {
  error.value = '';
  preview.value = null;
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = "L'accès à la webcam n'est pas disponible : il exige une connexion sécurisée "
      + '(https). Utilisez le bouton Parcourir… pour choisir un fichier image.';
    return;
  }
  try {
    // Résolution demandée nettement supérieure au besoin : le recadrage 35/45 jette une bonne
    // partie d'une image 4/3, autant partir de large. `ideal` et non `exact` : une webcam qui ne
    // sait pas faire doit fournir ce qu'elle peut, jamais échouer.
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
  } catch (e: any) {
    // Distinguer le refus des autres pannes : c'est la seule erreur que l'utilisateur peut corriger
    // lui-même, et elle n'a rien à voir avec une webcam absente ou déjà occupée.
    streaming.value = false;
    error.value = e?.name === 'NotAllowedError'
      ? "L'accès à la webcam a été refusé. Autorisez-le dans votre navigateur, puis réessayez."
      : "Aucune webcam disponible (elle est peut-être utilisée par une autre application).";
    return;
  }

  // Démarrage de la lecture, DEHORS du try ci-dessus : à ce stade le flux est bel et bien obtenu.
  // Un `play()` qui échoue (politique de démarrage automatique du navigateur, implémentation
  // partielle) ne veut pas dire « pas de webcam » — l'élément porte `autoplay`, l'image arrive de
  // toute façon. Le confondre avec une panne de caméra afficherait un message faux et retirerait le
  // bouton de capture alors que tout va bien (constaté en test).
  if (videoRef.value) {
    videoRef.value.srcObject = stream;
    try {
      await Promise.resolve(videoRef.value.play?.());
    } catch {
      /* sans conséquence, voir ci-dessus */
    }
  }
  streaming.value = true;
}

function stop() {
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  streaming.value = false;
  if (videoRef.value) videoRef.value.srcObject = null;
}

function capture() {
  const video = videoRef.value;
  if (!video || !video.videoWidth) return;

  const crop = computeCropRect(video.videoWidth, video.videoHeight, props.ratio);
  const canvas = document.createElement('canvas');
  canvas.width = props.outputWidth;
  canvas.height = Math.round(props.outputWidth / props.ratio);
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.drawImage(video, crop.x, crop.y, crop.width, crop.height, 0, 0, canvas.width, canvas.height);
  // JPEG et non PNG : une photo est une image continue, le PNG y serait dix fois plus lourd pour
  // rien — et cette valeur est stockée en base64 dans la base (voir core/upload_limits.py).
  preview.value = canvas.toDataURL('image/jpeg', 0.92);
  stop();
}

function retake() {
  preview.value = null;
  start();
}

function confirm() {
  if (!preview.value) return;
  emit('capture', {
    filename: 'photo.jpg',
    mime_type: 'image/jpeg',
    data_base64: preview.value.split(',')[1] || '',
  });
  close();
}

function close() {
  stop();
  preview.value = null;
  emit('update:modelValue', false);
}

// L'ouverture démarre le flux, la fermeture le coupe — un flux laissé ouvert garde la webcam
// allumée (témoin lumineux compris) alors que l'utilisateur a quitté l'écran.
watch(() => props.modelValue, open => (open ? start() : stop()));
onBeforeUnmount(stop);

// AUCUN effet miroir, ni au cadrage ni à la capture (décision explicite de l'utilisateur).
//
// L'inversion horizontale de l'aperçu est pourtant l'usage courant — on se cadre plus naturellement
// en se voyant comme dans une glace. Elle a été retirée parce qu'elle crée un décrochage au moment
// du déclenchement : `drawImage` lit les pixels réels du flux et ignore toute transformation CSS,
// la photo obtenue n'est donc jamais inversée. L'image « sautait » sous les yeux de l'utilisateur,
// qui y voyait un défaut plutôt qu'un choix. Cadrage et résultat sont désormais identiques.
//
// Ne pas réintroduire `transform: scaleX(-1)` sur la vidéo sans inverser AUSSI le canvas : une
// photo d'identité en miroir est non conforme, et tout texte à l'image (badge, vêtement) y serait
// illisible.
</script>

<style scoped>
.capture-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.capture-error {
  width: 100%;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-danger, #DC2626);
  background: color-mix(in srgb, var(--color-danger, #DC2626) 8%, transparent);
  color: var(--text-primary);
  font-size: 0.9rem;
}

/* Le cadre EST le format de la photo : la scène porte le ratio, la vidéo la remplit en `cover`.
   C'est la traduction visuelle exacte de computeCropRect (plus grand rectangle au bon ratio,
   centré) — les deux doivent rester cohérents, sinon le gabarit ment. */
.capture-stage {
  position: relative;
  max-height: 58vh;
  height: 420px;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #000;
}

.capture-video,
.capture-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}


.capture-guide {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.capture-hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 8px;
  text-align: center;
  color: #fff;
  font-size: 0.85rem;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
  pointer-events: none;
}
</style>

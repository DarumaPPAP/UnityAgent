using System;
using UnityEngine;

namespace CameraWorks
{
    public enum E_CAMERA_MOVE
    {
        Fix, FixPerfect, FixShake,
        PanLeft, PanRight, PanLeftUp, PanRightUp, PanLeftDown, PanRightDown,
        TiltUp, TiltDown, ZoomIn, ZoomOut, DollyIn, DollyOut,
        TrackLeft, TrackRight, TrackUp, TrackDown,
        TrackLeftUp, TrackRightUp, TrackLeftDown, TrackRightDown,
        CircleLeft, CircleRight, RollLeft, RollRight
    }

    public readonly struct S_CAMERA_PHASE
    {
        public E_CAMERA_MOVE[] Moves { get; }

        public S_CAMERA_PHASE(params E_CAMERA_MOVE[] moves)
        {
            Moves = moves ?? Array.Empty<E_CAMERA_MOVE>();
        }
    }

    public readonly struct S_CAMERA_CUT
    {
        public int No { get; }
        public string Label { get; }
        public int Count { get; }
        public S_CAMERA_PHASE[] Phases { get; }

        public S_CAMERA_CUT(int no, string label, int count, S_CAMERA_PHASE[] phases)
        {
            No = no;
            Label = label;
            Count = count;
            Phases = phases ?? Array.Empty<S_CAMERA_PHASE>();
        }
    }

    [RequireComponent(typeof(Camera))]
    public sealed class CameraWork : MonoBehaviour
    {
        [SerializeField, Min(0.05f)] private float _phaseDuration = 1.5f;
        [SerializeField, Min(0f)] private float _panAngle = 35f;
        [SerializeField, Min(0f)] private float _tiltAngle = 20f;
        [SerializeField, Min(0f)] private float _zoomAngle = 12f;
        [SerializeField, Min(0f)] private float _dollyDistance = 2f;
        [SerializeField, Min(0f)] private float _trackDistance = 2f;
        [SerializeField, Min(0f)] private float _circleAngle = 40f;
        [SerializeField, Min(0f)] private float _rollAngle = 360f;

        private Camera _camera;
        private S_CAMERA_CUT _cut;
        private S_CAMERA_PHASE _phase;
        private Vector3 _startPosition;
        private Quaternion _startRotation;
        private float _startFov;
        private float _elapsed;
        private int _phaseIndex;
        private bool _playing;

        public Transform Target { get; set; }
        public bool IsPlaying => _playing;
        public int PhaseIndex => _phaseIndex;

        private void Awake()
        {
            _camera = GetComponent<Camera>();
        }

        private void Update()
        {
            if (!_playing)
            {
                return;
            }

            _elapsed += Time.deltaTime;
            while (_playing && _elapsed >= _phaseDuration)
            {
                Sample(1f);
                _elapsed -= _phaseDuration;
                _phaseIndex++;

                if (_phaseIndex >= _cut.Phases.Length)
                {
                    _playing = false;
                    return;
                }

                Begin(_cut.Phases[_phaseIndex]);
            }

            if (_playing)
            {
                Sample(_elapsed / _phaseDuration);
            }
        }

        public void Play(S_CAMERA_CUT cut)
        {
            if (cut.Phases == null || cut.Phases.Length == 0)
            {
                throw new ArgumentException("At least one camera phase is required.", nameof(cut));
            }

            _cut = cut;
            _phaseIndex = 0;
            _elapsed = 0f;
            _playing = true;
            Begin(cut.Phases[0]);
            Sample(0f);
        }

        public void Begin(S_CAMERA_PHASE phase)
        {
            if (_camera == null)
            {
                _camera = GetComponent<Camera>();
            }

            _phase = phase;
            _startPosition = transform.position;
            _startRotation = transform.rotation;
            _startFov = _camera.fieldOfView;
        }

        public void Sample(float normalized)
        {
            float t = Mathf.Clamp01(normalized);
            float yaw = 0f;
            float pitch = 0f;
            float roll = 0f;
            float dolly = 0f;
            float lateral = 0f;
            float vertical = 0f;
            float circle = 0f;
            float zoom = 0f;
            float shake = 0f;

            foreach (E_CAMERA_MOVE move in _phase.Moves ?? Array.Empty<E_CAMERA_MOVE>())
            {
                switch (move)
                {
                    case E_CAMERA_MOVE.Fix: shake += 0.015f; break;
                    case E_CAMERA_MOVE.FixPerfect: break;
                    case E_CAMERA_MOVE.FixShake: shake += 0.12f; break;
                    case E_CAMERA_MOVE.PanLeft: yaw -= _panAngle; break;
                    case E_CAMERA_MOVE.PanRight: yaw += _panAngle; break;
                    case E_CAMERA_MOVE.PanLeftUp: yaw -= _panAngle; pitch += _tiltAngle; break;
                    case E_CAMERA_MOVE.PanRightUp: yaw += _panAngle; pitch += _tiltAngle; break;
                    case E_CAMERA_MOVE.PanLeftDown: yaw -= _panAngle; pitch -= _tiltAngle; break;
                    case E_CAMERA_MOVE.PanRightDown: yaw += _panAngle; pitch -= _tiltAngle; break;
                    case E_CAMERA_MOVE.TiltUp: pitch += _tiltAngle; break;
                    case E_CAMERA_MOVE.TiltDown: pitch -= _tiltAngle; break;
                    case E_CAMERA_MOVE.ZoomIn: zoom -= _zoomAngle; break;
                    case E_CAMERA_MOVE.ZoomOut: zoom += _zoomAngle; break;
                    case E_CAMERA_MOVE.DollyIn: dolly += _dollyDistance; break;
                    case E_CAMERA_MOVE.DollyOut: dolly -= _dollyDistance; break;
                    case E_CAMERA_MOVE.TrackLeft: lateral -= _trackDistance; break;
                    case E_CAMERA_MOVE.TrackRight: lateral += _trackDistance; break;
                    case E_CAMERA_MOVE.TrackUp: vertical += _trackDistance; break;
                    case E_CAMERA_MOVE.TrackDown: vertical -= _trackDistance; break;
                    case E_CAMERA_MOVE.TrackLeftUp: lateral -= _trackDistance; vertical += _trackDistance; break;
                    case E_CAMERA_MOVE.TrackRightUp: lateral += _trackDistance; vertical += _trackDistance; break;
                    case E_CAMERA_MOVE.TrackLeftDown: lateral -= _trackDistance; vertical -= _trackDistance; break;
                    case E_CAMERA_MOVE.TrackRightDown: lateral += _trackDistance; vertical -= _trackDistance; break;
                    case E_CAMERA_MOVE.CircleLeft: circle -= _circleAngle; break;
                    case E_CAMERA_MOVE.CircleRight: circle += _circleAngle; break;
                    case E_CAMERA_MOVE.RollLeft: roll += _rollAngle; break;
                    case E_CAMERA_MOVE.RollRight: roll -= _rollAngle; break;
                }
            }

            Vector3 pivot = Target != null ? Target.position : _startPosition + _startRotation * Vector3.forward * 6f;
            Quaternion orbit = Quaternion.AngleAxis(circle * t, Vector3.up);
            Vector3 position = pivot + orbit * (_startPosition - pivot);
            position += _startRotation * new Vector3(lateral * t, vertical * t, dolly * t);

            float wave = Mathf.Sin(t * Mathf.PI) * Mathf.Sin(t * Mathf.PI * 10f);
            position += _startRotation * new Vector3(wave * shake, Mathf.Sin(t * Mathf.PI * 14f) * Mathf.Sin(t * Mathf.PI) * shake, 0f);

            Quaternion rotation = _startRotation;
            if (!Mathf.Approximately(circle, 0f) && (pivot - position).sqrMagnitude > 0.0001f)
            {
                rotation = Quaternion.LookRotation(pivot - position, Vector3.up);
            }

            rotation = Quaternion.AngleAxis(yaw * t, Vector3.up) * rotation;
            rotation *= Quaternion.AngleAxis(-pitch * t, Vector3.right);
            rotation *= Quaternion.AngleAxis(roll * t + wave * shake * 25f, Vector3.forward);

            transform.SetPositionAndRotation(position, rotation);
            _camera.fieldOfView = Mathf.Clamp(_startFov + zoom * t, 1f, 179f);
        }

        public void Stop()
        {
            _playing = false;
        }
    }
}

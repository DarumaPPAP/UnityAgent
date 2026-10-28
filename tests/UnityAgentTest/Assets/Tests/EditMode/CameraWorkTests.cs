using System;
using System.Linq;
using CameraWorks;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Tests
{
    public sealed class CameraWorkTests
    {
        private GameObject _cameraObject;
        private Camera _camera;
        private CameraWork _work;

        [SetUp]
        public void SetUp()
        {
            _cameraObject = new GameObject("Camera Work Test");
            _camera = _cameraObject.AddComponent<Camera>();
            _work = _cameraObject.AddComponent<CameraWork>();
            _camera.fieldOfView = 60f;
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_cameraObject);
        }

        [Test]
        public void CatalogCoversAllCuts()
        {
            TextAsset data = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/CameraWork/Resources/CameraWorkCuts.txt");
            Assert.That(data, Is.Not.Null);

            var cuts = CameraWorkCatalog.Parse(data.text);
            Assert.That(cuts.Count, Is.EqualTo(196));
            Assert.That(cuts.Sum(cut => cut.Count), Is.EqualTo(1166));
            Assert.That(cuts.All(cut => cut.Phases.Length > 0 && cut.Phases.All(phase => phase.Moves.Length > 0)), Is.True);
            Assert.That(cuts[41].Phases.Length, Is.GreaterThan(10));
            Assert.That(cuts[125].Phases.Length, Is.GreaterThan(10));
        }

        [Test]
        public void CombinedMovesKeepSequentialAndSimultaneousPhases()
        {
            S_CAMERA_PHASE[] phases = CameraWorkCatalog.ParsePhases("フィクス→右パンドリーイン→左サークル");
            Assert.That(phases.Length, Is.EqualTo(3));
            Assert.That(phases[0].Moves, Is.EquivalentTo(new[] { E_CAMERA_MOVE.Fix }));
            Assert.That(phases[1].Moves, Is.EquivalentTo(new[] { E_CAMERA_MOVE.PanRight, E_CAMERA_MOVE.DollyIn }));
            Assert.That(phases[2].Moves, Is.EquivalentTo(new[] { E_CAMERA_MOVE.CircleLeft }));
        }

        [Test]
        public void UnknownWorkIsRejected()
        {
            Assert.Throws<FormatException>(() => CameraWorkCatalog.ParsePhases("未知の移動"));
        }

        [Test]
        public void PerfectFixDoesNotChangePose()
        {
            _cameraObject.transform.position = new Vector3(1f, 2f, -8f);
            Vector3 original = _cameraObject.transform.position;
            Quaternion rotation = _cameraObject.transform.rotation;
            _work.Begin(new S_CAMERA_PHASE(E_CAMERA_MOVE.FixPerfect));
            _work.Sample(0.37f);
            Assert.That(Vector3.Distance(original, _cameraObject.transform.position), Is.LessThan(0.0001f));
            Assert.That(Quaternion.Angle(rotation, _cameraObject.transform.rotation), Is.LessThan(0.0001f));
            Assert.That(_camera.fieldOfView, Is.EqualTo(60f).Within(0.0001f));
        }

        [Test]
        public void ZoomChangesFovButDollyChangesPosition()
        {
            _work.Begin(new S_CAMERA_PHASE(E_CAMERA_MOVE.ZoomIn));
            _work.Sample(1f);
            Assert.That(_camera.fieldOfView, Is.LessThan(60f));
            Assert.That(_cameraObject.transform.position, Is.EqualTo(Vector3.zero));

            _camera.fieldOfView = 60f;
            _work.Begin(new S_CAMERA_PHASE(E_CAMERA_MOVE.DollyIn));
            _work.Sample(1f);
            Assert.That(_cameraObject.transform.position.z, Is.GreaterThan(1f));
            Assert.That(_camera.fieldOfView, Is.EqualTo(60f).Within(0.0001f));
        }

        [Test]
        public void TrackChangesPositionWithoutChangingOrientation()
        {
            Quaternion original = _cameraObject.transform.rotation;
            _work.Begin(new S_CAMERA_PHASE(E_CAMERA_MOVE.TrackRight));
            _work.Sample(1f);
            Assert.That(_cameraObject.transform.position.x, Is.GreaterThan(1f));
            Assert.That(Quaternion.Angle(original, _cameraObject.transform.rotation), Is.LessThan(0.0001f));
        }

        [Test]
        public void CirclePreservesRadiusAndLooksAtTarget()
        {
            var target = new GameObject("Target");
            try
            {
                _cameraObject.transform.position = new Vector3(0f, 0f, -8f);
                _cameraObject.transform.LookAt(target.transform.position);
                _work.Target = target.transform;
                _work.Begin(new S_CAMERA_PHASE(E_CAMERA_MOVE.CircleRight));
                _work.Sample(1f);
                Assert.That(Vector3.Distance(_cameraObject.transform.position, target.transform.position), Is.EqualTo(8f).Within(0.001f));
                Vector3 toTarget = (target.transform.position - _cameraObject.transform.position).normalized;
                Assert.That(Vector3.Dot(_cameraObject.transform.forward, toTarget), Is.GreaterThan(0.999f));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(target);
            }
        }
    }
}

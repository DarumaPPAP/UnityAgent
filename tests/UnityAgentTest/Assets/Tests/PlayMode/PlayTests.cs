using System;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace DarumaPPAP.UnityAgent.Tests
{
    public sealed class PlayTests
    {
        private Scene scene;
        private GameObject probeObject;

        [UnityTest]
        public IEnumerator ComponentStartsInOwnedScene()
        {
            scene = SceneManager.CreateScene("UnityAgentSmoke-" + Guid.NewGuid().ToString("N"));
            probeObject = new GameObject("LifecycleProbe");
            SceneManager.MoveGameObjectToScene(probeObject, scene);
            var probe = probeObject.AddComponent<PlayTestsProbe>();
            Assert.That(probe.WasAwake, Is.True);
            yield return null;
            Assert.That(probe.WasStarted, Is.True);
            Assert.That(probeObject.scene, Is.EqualTo(scene));
            Assert.That(scene.isLoaded, Is.True);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            if (probeObject != null)
                UnityEngine.Object.Destroy(probeObject);
            if (scene.IsValid() && scene.isLoaded)
                yield return SceneManager.UnloadSceneAsync(scene);
        }
    }

    public sealed class PlayTestsProbe : MonoBehaviour
    {
        public bool WasAwake { get; private set; }
        public bool WasStarted { get; private set; }

        private void Awake() => WasAwake = true;
        private void Start() => WasStarted = true;
    }
}

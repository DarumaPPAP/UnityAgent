using CameraWorks;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class CameraWorkDemoMenu
{
    [MenuItem("Tools/MyTools/Camera Works/Create Demo Scene")]
    private static void CreateDemoScene()
    {
        // 既存Sceneは保存せず、テスト専用の未保存Sceneへ切り替える。
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        var target = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        target.name = "Focus";
        target.transform.position = new Vector3(0f, 1.7f, 0f);
        target.transform.localScale = new Vector3(1.6f, 1.6f, 1.6f);

        var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
        floor.name = "Floor";
        floor.transform.position = new Vector3(0f, -0.2f, 0f);
        floor.transform.localScale = new Vector3(16f, 0.3f, 16f);

        for (int x = -2; x <= 2; x++)
        {
            for (int z = -2; z <= 2; z++)
            {
                if (x == 0 && z == 0)
                {
                    continue;
                }

                var marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
                marker.name = $"Marker {x} {z}";
                marker.transform.position = new Vector3(x * 2.5f, 0.6f, z * 2.5f);
                marker.transform.localScale = new Vector3(0.8f, 1.2f + (x + 2) * 0.15f, 0.8f);
            }
        }

        var lightObject = new GameObject("Key Light");
        var light = lightObject.AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 1.2f;
        lightObject.transform.rotation = Quaternion.Euler(40f, -35f, 0f);

        var cameraObject = new GameObject("Demo Camera");
        var camera = cameraObject.AddComponent<Camera>();
        cameraObject.AddComponent<AudioListener>();
        cameraObject.tag = "MainCamera";
        camera.fieldOfView = 60f;
        cameraObject.transform.position = new Vector3(0f, 3.2f, -12f);
        cameraObject.transform.LookAt(target.transform.position);

        var work = cameraObject.AddComponent<CameraWork>();
        work.Target = target.transform;
        var demo = cameraObject.AddComponent<CameraWorkDemo>();
        demo.Catalog = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/CameraWork/Resources/CameraWorkCuts.txt");

        Selection.activeGameObject = cameraObject;
        EditorSceneManager.MarkSceneDirty(scene);
        Debug.Log("Camera Work Demoを生成しました。Playで基本技法と196種類のカットを確認できます。Scene保存は任意です。");
    }
}
